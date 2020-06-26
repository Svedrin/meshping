#!/usr/bin/python
# -*- coding: utf-8 -*-
# kate: space-indent on; indent-width 4; replace-tabs on;

import json
import os
import os.path
import math
import socket
import sys

from uuid       import uuid4
from time       import time
from quart_trio import QuartTrio
from redis      import StrictRedis

import trio

from oping import PingObj, PingError
from api   import add_api_views
from peers import run_peers
from db    import Database, OperationalError

INTERVAL = 30

FAC_15m = math.exp(-INTERVAL / (     15 * 60.))
FAC_6h  = math.exp(-INTERVAL / ( 6 * 60 * 60.))
FAC_24h = math.exp(-INTERVAL / (24 * 60 * 60.))


class MeshPing:
    def __init__(self, db, timeout=5, interval=30):
        assert interval > timeout, "Interval must be larger than the timeout"
        self.db = db
        self.timeout  = timeout
        self.interval = interval

    def all_targets(self):
        return self.db.all_targets()

    def add_target(self, target):
        assert "@" in target
        name, addr = target.split("@", 1)
        self.db.add_target(addr, name)

    def remove_target(self, target):
        assert "@" in target
        name, addr = target.split("@", 1)
        self.db.delete_target(addr)

    def get_target_stats(self, addr):
        stats = {
            "sent": 0, "lost": 0, "recv": 0, "last": 0, "sum":  0, "min":  0, "max":  0
        }
        stats.update(self.db.get_statistics(addr))
        return stats

    def get_target_histogram(self, addr):
        return self.db.get_histogram(addr)

    def clear_stats(self):
        raise NotImplementedError("clear_stats")

    async def run(self):
        pingobj = PingObj()
        pingobj.set_timeout(self.timeout)

        next_ping = time() + 0.1

        current_targets = set()

        while True:
            now = time()
            next_ping = now + self.interval

            unseen_targets = current_targets.copy()
            for target in self.db.all_targets():
                if target.addr not in current_targets:
                    current_targets.add(target.addr)
                    pingobj.add_host(target.addr.encode("utf-8"))
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
                if time() < next_ping:
                    await trio.sleep(next_ping - time())
                continue

            # We do have targets, so first, let's ping them
            await trio.to_thread.run_sync(
                lambda: pingobj.send()
            )

            for hostinfo in pingobj.get_hosts():
                hostinfo["addr"] = hostinfo["addr"].decode("utf-8")

                try:
                    target_stats = self.get_target_stats(hostinfo["addr"])
                except LookupError:
                    # ping takes a while. it's possible that while we were busy, this
                    # target has been deleted from the DB. If so, ignore it.
                    if hostinfo["addr"] in current_targets:
                        current_targets.remove(hostinfo["addr"])

                histogram = self.get_target_histogram(hostinfo["addr"])

                target_stats["sent"] += 1

                if hostinfo["latency"] != -1:
                    target_stats["recv"] += 1
                    target_stats["last"]  = hostinfo["latency"]
                    target_stats["sum"]  += target_stats["last"]
                    target_stats["max"]   = max(target_stats["max"], target_stats["last"])

                    if target_stats["min"] == 0:
                        target_stats["min"] = target_stats["last"]
                    else:
                        target_stats["min"] = min(target_stats["min"], target_stats["last"])

                    if "avg15m" not in target_stats:
                        target_stats["avg15m"] = target_stats["last"]
                    else:
                        target_stats["avg15m"] = (target_stats["avg15m"] * FAC_15m) + (target_stats["last"] * (1 - FAC_15m))

                    if "avg6h" not in target_stats:
                        target_stats["avg6h"] = target_stats["last"]
                    else:
                        target_stats["avg6h"] = (target_stats["avg6h"] * FAC_6h) + (target_stats["last"] * (1 - FAC_6h))

                    if "avg24h" not in target_stats:
                        target_stats["avg24h"] = target_stats["last"]
                    else:
                        target_stats["avg24h"] = (target_stats["avg24h"] * FAC_24h) + (target_stats["last"] * (1 - FAC_24h))

                    self.db.add_measurement(
                        hostinfo["addr"],
                        timestamp = now // 3600 * 3600,
                        bucket    = int(math.log(hostinfo["latency"], 2) * 10)
                    )

                else:
                    target_stats["lost"] += 1

                self.db.update_statistics(hostinfo["addr"], target_stats)

            if time() < next_ping:
                await trio.sleep(next_ping - time())

def main():
    if os.getuid() != 0:
        raise RuntimeError("need to be root, sorry about that")

    known_env_vars = (
        "MESHPING_DATABASE_PATH",
        "MESHPING_REDIS_HOST",
        "MESHPING_PING_TIMEOUT",
        "MESHPING_PING_INTERVAL",
        "MESHPING_PEERS",
        "MESHPING_PROMETHEUS_URL",
        "MESHPING_PROMETHEUS_QUERY",
    )

    for key in os.environ.keys():
        if key.startswith("MESHPING_") and key not in known_env_vars:
            print("env var %s is unknown" % key, file=sys.stderr)
            sys.exit(1)

    app = QuartTrio(__name__, static_url_path="")
    #app.config["TEMPLATES_AUTO_RELOAD"] = True
    app.secret_key = str(uuid4())

    try:
        db_path = os.path.join(os.environ.get("MESHPING_DATABASE_PATH", "db"), "meshping.db")
        db = Database(db_path)
    except OperationalError as err:
        print("Could not open database %s: %s" % (db_path, err), file=sys.stderr)
        return 2

    if "MESHPING_REDIS_HOST" in os.environ:
        redis = StrictRedis(host=os.environ["MESHPING_REDIS_HOST"])

        # Transition period: Read all targets from redis and add them to our DB
        for target in redis.smembers("meshping:targets"):
            target = target.decode("utf-8")
            name, addr = target.split("@", 1)
            db.add_target(addr, name)

    mp = MeshPing(
        db,
        int(os.environ.get("MESHPING_PING_TIMEOUT",   5)),
        int(os.environ.get("MESHPING_PING_INTERVAL", 30))
    )

    add_api_views(app, mp)

    @app.before_serving
    async def startup():
        app.nursery.start_soon(mp.run)
        app.nursery.start_soon(run_peers, mp)

    app.run(host="::", port=9922, debug=False, use_reloader=False)

if __name__ == '__main__':
    main()
