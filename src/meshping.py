#!/usr/bin/python
# -*- coding: utf-8 -*-
# kate: space-indent on; indent-width 4; replace-tabs on;

import os
import os.path
import math
import sys
import logging

from uuid       import uuid4
from time       import time
from markupsafe import Markup
from quart_trio import QuartTrio
from icmplib    import traceroute
from ipwhois    import IPWhois, IPDefinedError
from netaddr    import IPAddress, IPNetwork

import trio

from oping import PingObj, PingError
from api   import add_api_views
from peers import run_peers
from db    import Target
from socklib import reverse_lookup, ip_pmtud

INTERVAL = 30

FAC_15m = math.exp(-INTERVAL / (     15 * 60.))
FAC_6h  = math.exp(-INTERVAL / ( 6 * 60 * 60.))
FAC_24h = math.exp(-INTERVAL / (24 * 60 * 60.))

def exp_avg(current_avg, add_value, factor):
    if current_avg is None:
        return add_value
    return (current_avg * factor) + (add_value * (1 - factor))

async def sleep_until(when):
    now = time()
    if now < when:
        await trio.sleep(when - now)

class MeshPing:
    def __init__(self, timeout=5, interval=30, histogram_days=3, traceroute_interval=900):
        assert interval > timeout, "Interval must be larger than the timeout"
        self.timeout  = timeout
        self.interval = interval
        self.histogram_period = histogram_days * 86400
        self.traceroute_interval = traceroute_interval

        self.whois_cache = {}

    def all_targets(self):
        return Target.db.all()

    def add_target(self, target):
        assert "@" in target
        name, addr = target.split("@", 1)
        Target.db.add(addr, name)

    def remove_target(self, addr):
        Target.db.get(addr).delete()

    def get_target(self, addr):
        return Target.db.get(addr)

    def clear_statistics(self):
        Target.db.clear_statistics()

    async def run_traceroutes(self):
        while True:
            now = time()
            next_run = now + self.traceroute_interval
            pmtud_cache = {}
            for target in Target.db.all():
                trace = await trio.to_thread.run_sync(
                    lambda tgtaddr: traceroute(tgtaddr, fast=True, timeout=0.5, count=1),
                    target.addr
                )

                hopaddrs = [hop.address for hop in trace]
                hoaddrs_set = set(hopaddrs)
                target.set_route_loop(
                    len(hopaddrs) != len(hoaddrs_set) and len(hoaddrs_set) > 1
                )

                trace_hops = []
                for hop in trace:
                    if hop.address not in pmtud_cache:
                        pmtud_cache[hop.address] = ip_pmtud(hop.address)

                    trace_hops.append({
                        "name":    reverse_lookup(hop.address),
                        "distance":hop.distance,
                        "address": hop.address,
                        "max_rtt": hop.max_rtt,
                        "pmtud":   pmtud_cache[hop.address],
                        "whois":   self.whois(hop.address),
                        "time":    now,
                    })

                target.set_traceroute(trace_hops)

                # Running a bunch'a traceroutes all at once might trigger our default
                # gw's rate limiting if it receives too many packets with a ttl of 1
                # too quickly. Let's go a bit slower so that it doesn't stop sending
                # "ttl exceeded" replies and messing up our results.
                await trio.sleep(2)

            await sleep_until(next_run)


    def whois(self, hop_address):
        # If we know this address already and it's up-to-date, skip it
        now = int(time())
        if (
            hop_address in self.whois_cache and
            self.whois_cache[hop_address].get("last_check", 0) + 72*3600 < now
        ):
            return self.whois_cache[hop_address]

        # Check if the IP is private or reserved
        addr = IPAddress(hop_address)
        if (addr.version == 4 and (
            addr in IPNetwork("10.0.0.0/8")     or
            addr in IPNetwork("172.16.0.0/12")  or
            addr in IPNetwork("192.168.0.0/16") or
            addr in IPNetwork("100.64.0.0/10")
        )) or (
            addr.version == 6 and
            addr not in IPNetwork("2000::/3")
        ):
            return {}

        # It's not, look up whois info
        try:
            self.whois_cache[hop_address] = dict(
                IPWhois(hop_address).lookup_rdap(),
                last_check=now
            )
        except IPDefinedError:
            # RFC1918, RFC6598 or something else
            return {}
        except Exception as err:
            logging.warning("Could not query whois for IP %s: %s", hop_address, err)
        return self.whois_cache[hop_address]

    async def run(self):
        pingobj = PingObj()
        pingobj.set_timeout(self.timeout)

        next_ping = time() + 0.1

        current_targets = set()

        while True:
            now = time()
            next_ping = now + self.interval

            # Run DB housekeeping
            Target.db.prune_histograms(before_timestamp=(now - self.histogram_period))

            unseen_targets = current_targets.copy()
            for target in Target.db.all():
                if target.addr not in current_targets:
                    current_targets.add(target.addr)
                    try:
                        pingobj.add_host(target.addr.encode("utf-8"))
                    except PingError as err:
                        target.set_error(err.args[0].decode("utf-8"))
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
                await sleep_until(next_ping)
                continue

            # We do have targets, so first, let's ping them
            await trio.to_thread.run_sync(
                lambda: pingobj.send()
            )

            for hostinfo in pingobj.get_hosts():
                hostinfo["addr"] = hostinfo["addr"].decode("utf-8")

                try:
                    self.process_ping_result(now, hostinfo)
                except LookupError:
                    # ping takes a while. it's possible that while we were busy, this
                    # target has been deleted from the DB. If so, forget about it.
                    if hostinfo["addr"] in current_targets:
                        current_targets.remove(hostinfo["addr"])

            await sleep_until(next_ping)

    def process_ping_result(self, timestamp, hostinfo):
        target = self.get_target(hostinfo["addr"])
        target_stats = target.statistics
        target_stats["sent"] += 1

        if hostinfo["latency"] != -1:
            target.set_state("up")
            target_stats["recv"] += 1
            target_stats["last"]  = hostinfo["latency"]
            target_stats["sum"]  += target_stats["last"]
            target_stats["max"]   = max(target_stats.get("max", 0),            target_stats["last"])
            target_stats["min"]   = min(target_stats.get("min", float('inf')), target_stats["last"])
            target_stats["avg15m"] = exp_avg(target_stats.get("avg15m"), target_stats["last"], FAC_15m)
            target_stats["avg6h" ] = exp_avg(target_stats.get("avg6h"),  target_stats["last"], FAC_6h )
            target_stats["avg24h"] = exp_avg(target_stats.get("avg24h"), target_stats["last"], FAC_24h)

            target.add_measurement(
                timestamp = timestamp // 3600 * 3600,
                bucket    = int(math.log(hostinfo["latency"], 2) * 10)
            )

        else:
            target.set_state("down")
            target_stats["lost"] += 1

        target.update_statistics(target_stats)


def build_app():
    if os.getuid() != 0:
        raise RuntimeError("need to be root, sorry about that")

    known_env_vars = (
        "MESHPING_DATABASE_PATH",
        "MESHPING_PING_TIMEOUT",
        "MESHPING_PING_INTERVAL",
        "MESHPING_TRACEROUTE_INTERVAL",
        "MESHPING_HISTOGRAM_DAYS",
        "MESHPING_PEERS",
        "MESHPING_PEERING_INTERVAL",
        "MESHPING_PROMETHEUS_URL",
        "MESHPING_PROMETHEUS_QUERY",
        "MESHPING_REDIS_HOST",
        "MESHPING_DEV",
    )

    deprecated_env_vars = (
        "MESHPING_PROMETHEUS_URL",
        "MESHPING_PROMETHEUS_QUERY",
        "MESHPING_REDIS_HOST",
    )

    for key in os.environ:
        if key.startswith("MESHPING_") and key not in known_env_vars:
            print(f"env var {key} is unknown", file=sys.stderr)
            sys.exit(1)
        if key.startswith("MESHPING_") and key in deprecated_env_vars:
            print(f"env var {key} is deprecated, ignored", file=sys.stderr)

    app = QuartTrio(__name__, static_url_path="")

    if os.environ.get("MESHPING_DEV", "false") == "true":
        app.config["TEMPLATES_AUTO_RELOAD"] = True

    app.secret_key = str(uuid4())
    app.jinja_options = dict(
        variable_start_string = '{[',
        variable_end_string   = ']}'
    )

    @app.context_processor
    def _inject_icons():
        # I'm not happy about hardcoding this path here, but I'm also not sure what else to do
        icons_dir = "/opt/meshping/ui/node_modules/bootstrap-icons/icons/"
        return dict(
            icons={
                filename: Markup(open(os.path.join(icons_dir, filename), "r").read())
                for filename in os.listdir(icons_dir)
            }
        )

    mp = MeshPing(
        int(os.environ.get("MESHPING_PING_TIMEOUT",          5)),
        int(os.environ.get("MESHPING_PING_INTERVAL",        30)),
        int(os.environ.get("MESHPING_HISTOGRAM_DAYS",        3)),
        int(os.environ.get("MESHPING_TRACEROUTE_INTERVAL", 900))
    )

    add_api_views(app, mp)

    @app.before_serving
    async def _():
        app.nursery.start_soon(mp.run)
        app.nursery.start_soon(mp.run_traceroutes)
        app.nursery.start_soon(run_peers, mp)

    return app

app = build_app()

if __name__ == '__main__':
    app.run(host="::", port=9922, debug=False, use_reloader=False)
