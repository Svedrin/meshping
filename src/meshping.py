#!/usr/bin/python
# -*- coding: utf-8 -*-
# kate: space-indent on; indent-width 4; replace-tabs on;

import json
import os
import os.path
import math
import socket

from uuid       import uuid4
from time       import time
from quart_trio import QuartTrio
from redis      import StrictRedis

import trio

from oping import PingObj, PingError
from api   import add_api_views
from peers import run_peers

INTERVAL = 30

FAC_15m = math.exp(-INTERVAL / (     15 * 60.))
FAC_6h  = math.exp(-INTERVAL / ( 6 * 60 * 60.))
FAC_24h = math.exp(-INTERVAL / (24 * 60 * 60.))


class MeshPing:
    def __init__(self, redis, timeout=1):
        self.targets = {}
        self.histograms = {}
        self.timeout  = timeout
        self.redis = redis

    def redis_load(self, addr, field):
        rds_value = self.redis.get("meshping:%s:%s:%s" % (socket.gethostname(), addr, field))
        if rds_value is None:
            return None
        return json.loads(rds_value)

    def iter_targets(self):
        for target in self.redis.smembers("meshping:targets"):
            target = target.decode("utf-8")
            name, addr = target.split("@", 1)
            yield target, name, addr

    def add_target(self, target):
        assert "@" in target
        self.redis.sadd("meshping:targets", target)
        self.redis.srem("meshping:foreign_targets", target)

    def remove_target(self, target):
        assert "@" in target
        self.redis.srem("meshping:targets", target)
        self.redis.srem("meshping:foreign_targets", target)

    def get_target_info(self, addr, name_if_created):
        if addr not in self.targets:
            self.targets[addr] = self.redis_load(addr, "target") or {
                "name": name_if_created, "addr": addr,
                "sent": 0, "lost": 0, "recv": 0, "last": 0, "sum":  0, "min":  0, "max":  0
            }
        return self.targets[addr]

    def get_target_histogram(self, addr):
        if addr not in self.histograms:
            histogram = self.redis_load(addr, "histogram") or {}
            # json sucks and converts dict keys to strings
            histogram = {int(x): y for (x, y) in histogram.items()}
            self.histograms[addr] = histogram
        return self.histograms[addr]

    def clear_stats(self):
        keys = self.redis.keys("meshping:%s:*" % socket.gethostname())
        rdspipe = self.redis.pipeline()
        for key in keys:
            self.redis.delete(key)
        rdspipe.execute()
        self.targets = {}
        self.histograms = {}

    async def run(self):
        pingobj = PingObj()
        pingobj.set_timeout(self.timeout)

        next_ping = time() + 0.1

        current_targets = set()

        while True:
            now = time()
            next_ping = now + 30

            unseen_targets = current_targets.copy()
            for target, name, addr in self.iter_targets():
                if target not in current_targets:
                    current_targets.add(target)
                    pingobj.add_host(addr.encode("utf-8"))
                    self.get_target_info(addr, name)["name"] = name
                if target in unseen_targets:
                    unseen_targets.remove(target)

            for target in unseen_targets:
                current_targets.remove(target)
                name, addr = target.split("@", 1)
                try:
                    pingobj.remove_host(addr.encode("utf-8"))
                except PingError:
                    # Host probably not there anyway
                    pass
                self.targets.pop(addr, None)
                self.histograms.pop(addr, None)

            if not current_targets:
                await trio.sleep(next_ping - time())
                continue

            await trio.to_thread.run_sync(
                lambda: pingobj.send()
            )

            rdspipe = self.redis.pipeline()

            for hostinfo in pingobj.get_hosts():
                hostinfo["name"] = hostinfo["name"].decode("utf-8")
                hostinfo["addr"] = hostinfo["addr"].decode("utf-8")

                target    = self.get_target_info(hostinfo["addr"], hostinfo["name"])
                histogram = self.get_target_histogram(hostinfo["addr"])

                target["sent"] += 1

                if hostinfo["latency"] != -1:
                    target["recv"] += 1
                    target["last"]  = hostinfo["latency"]
                    target["sum"]  += target["last"]
                    target["max"]   = max(target["max"], target["last"])

                    if target["min"] == 0:
                        target["min"] = target["last"]
                    else:
                        target["min"] = min(target["min"], target["last"])

                    if "avg15m" not in target:
                        target["avg15m"] = target["last"]
                    else:
                        target["avg15m"] = (target["avg15m"] * FAC_15m) + (target["last"] * (1 - FAC_15m))

                    if "avg6h" not in target:
                        target["avg6h"] = target["last"]
                    else:
                        target["avg6h"] = (target["avg6h"] * FAC_6h) + (target["last"] * (1 - FAC_6h))

                    if "avg24h" not in target:
                        target["avg24h"] = target["last"]
                    else:
                        target["avg24h"] = (target["avg24h"] * FAC_24h) + (target["last"] * (1 - FAC_24h))

                    histbucket = int(math.log(hostinfo["latency"], 2) * 10)
                    histogram.setdefault(histbucket, 0)
                    histogram[histbucket] += 1

                else:
                    target["lost"] += 1

                rds_prefix = "meshping:%s:%s" % (socket.gethostname(), target["addr"])
                rdspipe.setex("%s:target"    % rds_prefix, 7 * 86400, json.dumps(target))
                rdspipe.setex("%s:histogram" % rds_prefix, 7 * 86400, json.dumps(histogram))

            rdspipe.execute()

            await trio.sleep(next_ping - time())

def main():
    if os.getuid() != 0:
        raise RuntimeError("need to be root, sorry about that")

    app = QuartTrio(__name__, static_url_path="")
    app.config["TEMPLATES_AUTO_RELOAD"] = True
    app.secret_key = str(uuid4())
    app.debug = False

    redis = StrictRedis(host=os.environ.get("MESHPING_REDIS_HOST", "127.0.0.1"))
    mp = MeshPing(redis, int(os.environ.get("MESHPING_PING_TIMEOUT", 5)))

    add_api_views(app, mp)

    @app.before_serving
    async def startup():
        app.nursery.start_soon(mp.run)
        app.nursery.start_soon(run_peers, mp)

    app.run(host="::", port=9922)

if __name__ == '__main__':
    main()
