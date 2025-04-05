import time
import math
from threading import Thread

# pylint cannot read the definitions in the shared object
# pylint: disable=no-name-in-module
from oping import PingObj, PingError
from ..models import Histogram, Target, Statistics, Meta, TargetState


INTERVAL = 30
FAC_15m = math.exp(-INTERVAL / (15 * 60.0))
FAC_6h = math.exp(-INTERVAL / (6 * 60 * 60.0))
FAC_24h = math.exp(-INTERVAL / (24 * 60 * 60.0))


class PingThread(Thread):
    def __init__(self, mp_config, *args, **kwargs):
        self.mp_config = mp_config
        super().__init__(*args, **kwargs)

    @staticmethod
    def exp_avg(current_avg, add_value, factor):
        if current_avg is None:
            return add_value
        return (current_avg * factor) + (add_value * (1 - factor))

    def process_ping_result(self, timestamp, hostinfo):
        target = Target.objects.filter(addr=hostinfo["addr"]).first()
        # TODO proper error handling instead of assert
        assert target is not None
        target_stats, _created = Statistics.objects.get_or_create(target=target)
        target_meta, _created = Meta.objects.get_or_create(target=target)

        target_stats.sent += 1

        if hostinfo["latency"] != -1:
            target_meta.state = TargetState.UP
            target_stats.recv += 1
            target_stats.last = hostinfo["latency"]
            target_stats.sum += target_stats.last
            target_stats.max = max(target_stats.max, target_stats.last)
            target_stats.min = min(target_stats.min, target_stats.last)
            target_stats.avg15m = self.exp_avg(
                target_stats.avg15m, target_stats.last, FAC_15m
            )
            target_stats.avg6h = self.exp_avg(
                target_stats.avg6h, target_stats.last, FAC_6h
            )
            target_stats.avg24h = self.exp_avg(
                target_stats.avg24h, target_stats.last, FAC_24h
            )

            bucket, _created = Histogram.objects.get_or_create(
                target=target,
                timestamp=timestamp // 3600 * 3600,
                bucket=int(math.log(hostinfo["latency"], 2) * 10),
            )
            bucket.count += 1
            bucket.save()

        else:
            target_meta.state = TargetState.DOWN
            target_stats.lost += 1

        target_stats.save()
        target_meta.save()

    def run(self):
        pingobj = PingObj()
        pingobj.set_timeout(self.mp_config.ping_timeout)

        next_ping = time.time() + 0.1

        current_targets = set()

        while True:
            now = time.time()
            next_ping = now + self.mp_config.ping_interval

            # Run DB housekeeping
            # TODO has nothing to do with pings, find a better place (probably new
            #      housekeeping thread)
            Histogram.objects.filter(
                timestamp__lt=(now - self.mp_config.histogram_period)
            ).delete()

            unseen_targets = current_targets.copy()
            for target in Target.objects.all():
                if target.addr not in current_targets:
                    current_targets.add(target.addr)
                    try:
                        pingobj.add_host(target.addr.encode("utf-8"))
                    except PingError as err:
                        # TODO make this safe, do not just assume the object exists
                        target_meta = Meta.objects.filter(target=target)[0]
                        target_meta.state = TargetState.ERROR
                        target_meta.error = err.args[0].decode("utf-8")
                        target_meta.save()
                if target.addr in unseen_targets:
                    unseen_targets.remove(target.addr)

            for target_addr in unseen_targets:
                current_targets.remove(target_addr)
                try:
                    pingobj.remove_host(target_addr.encode("utf-8"))
                except PingError:
                    # Host probably not there anyway
                    pass

            # If we don't have any targets, we're done for now -- just sleep
            if not current_targets:
                time.sleep(max(0, next_ping - time.time()))
                continue

            # We do have targets, so first, let's ping them
            pingobj.send()

            for hostinfo in pingobj.get_hosts():
                hostinfo["addr"] = hostinfo["addr"].decode("utf-8")

                try:
                    self.process_ping_result(now, hostinfo)
                except LookupError:
                    # ping takes a while. it's possible that while we were busy, this
                    # target has been deleted from the DB. If so, forget about it.
                    if hostinfo["addr"] in current_targets:
                        current_targets.remove(hostinfo["addr"])

            time.sleep(max(0, next_ping - time.time()))
