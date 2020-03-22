# -*- coding: utf-8 -*-

from __future__ import division

import socket

from uuid  import uuid4
from quart      import Response, render_template, request, jsonify, send_from_directory
from quart_trio import QuartTrio

from ifaces import Ifaces4

def run_prom(mp):
    app = QuartTrio(__name__, static_url_path="")
    app.config["TEMPLATES_AUTO_RELOAD"] = True

    @app.route("/")
    async def index():
        return await render_template("index.html", Hostname=socket.gethostname())

    @app.route("/metrics")
    async def metrics():
        respdata = ['\n'.join([
            '# HELP meshping_sent Sent pings',
            '# TYPE meshping_sent counter',
            '# HELP meshping_recv Received pongs',
            '# TYPE meshping_recv counter',
            '# HELP meshping_lost Lost pings (actual counter, not just sent - recv)',
            '# TYPE meshping_lost counter',
            '# HELP meshping_max max ping',
            '# TYPE meshping_max gauge',
            '# HELP meshping_min min ping',
            '# TYPE meshping_min gauge',
            '# HELP meshping_pings Pings bucketed by response time',
            '# TYPE meshping_pings histogram',
        ])]

        for addr, target in mp.targets.items():

            respdata.append('\n'.join([
                'meshping_sent{name="%(name)s",target="%(addr)s"} %(sent)d',

                'meshping_recv{name="%(name)s",target="%(addr)s"} %(recv)d',

                'meshping_lost{name="%(name)s",target="%(addr)s"} %(lost)d',
            ]) % target)

            if target["recv"]:
                target = dict(target, avg=(target["sum"] / target["recv"]))
                respdata.append('\n'.join([
                    'meshping_max{name="%(name)s",target="%(addr)s"} %(max).2f',

                    'meshping_min{name="%(name)s",target="%(addr)s"} %(min).2f',
                ]) % target)

            respdata.append('\n'.join([
                'meshping_pings_sum{name="%(name)s",target="%(addr)s"} %(sum)f',
                'meshping_pings_count{name="%(name)s",target="%(addr)s"} %(recv)d',
            ]) % target)

            histogram = mp.histograms.get(addr, {})
            buckets = sorted(histogram.keys(), key=float)
            count = 0
            for bucket in buckets:
                nextping = 2 ** ((bucket + 1) / 10.) - 0.01
                count += histogram[bucket]
                respdata.append('meshping_pings_bucket{name="%(name)s",target="%(addr)s",le="%(le).2f"} %(count)d' % dict(
                    addr  = addr,
                    count = count,
                    le    = nextping,
                    name  = target['name'],
                ))

        return Response('\n'.join(respdata) + '\n', mimetype="text/plain")

    @app.route("/peer", methods=["POST"])
    async def peer():
        # Allows peers to POST a json structure such as this:
        # {
        #    "targets": [
        #       { "name": "raspi",  "addr": "192.168.0.123", "local": true  },
        #       { "name": "google", "addr": "8.8.8.8",       "local": false }
        #    ]
        # }
        # The non-local targets will then be added to our target list
        # and stats will be returned for these targets (if known).
        # Local targets will only be added if they are also local to us.

        request_json = await request.get_json()

        if request_json is None:
            return "Please send content-type:application/json", 400

        if type(request_json.get("targets")) != list:
            return "need targets as a list", 400

        stats = []
        if4   = Ifaces4()

        for target in request_json["targets"]:
            if type(target) != dict:
                return "targets must be dicts", 400
            if ("name" not in target  or not target["name"].strip() or
                "addr" not in target  or not target["addr"].strip() or
                "local" not in target or type(target["local"]) != bool):
                return "required field missing in target", 400

            target["name"] = target["name"].strip()
            target["addr"] = target["addr"].strip()

            if if4.is_interface(target["addr"]):
                # no need to ping my own interfaces, ignore
                continue

            if target["local"] and not if4.is_local(target["addr"]):
                continue

            target_str = "%(name)s@%(addr)s" % target
            mp.redis.sadd("meshping:foreign_targets", target_str)
            mp.redis.sadd("meshping:targets", target_str)
            stats.append(mp.targets.get(target["addr"]))

        return jsonify(success=True, targets=stats)

    @app.route('/ui/<path:path>')
    async def send_js(path):
        resp = await send_from_directory('ui', path)
        # Cache bust XXL
        resp.cache_control.no_cache = True
        resp.cache_control.no_store = True
        resp.cache_control.max_age  = None
        resp.cache_control.must_revalidate = True
        return resp

    @app.route("/api/targets")
    async def targets():
        targets = []

        def ip_as_int(addr):
            import socket
            import struct
            if ":" not in addr:
                return struct.unpack("!I", socket.inet_aton(addr))[0]
            else:
                ret = 0
                for intpart in struct.unpack("!IIII", socket.inet_pton(socket.AF_INET6, addr)):
                    ret = ret<<32 | intpart
                return ret

        for targetinfo in mp.targets.values():
            loss = 0
            if targetinfo["sent"]:
                loss = (targetinfo["sent"] - targetinfo["recv"]) / targetinfo["sent"] * 100
            targets.append(
                dict(targetinfo,
                    name=targetinfo["name"][:24],
                    addr_as_int=ip_as_int(targetinfo["addr"]),
                    succ=100 - loss,
                    loss=loss,
                    avg15m=targetinfo.get("avg15m", 0),
                    avg6h =targetinfo.get("avg6h",  0),
                    avg24h=targetinfo.get("avg24h", 0),
                )
            )

        return jsonify(success=True, targets=targets)

    app.secret_key = str(uuid4())
    app.debug = False

    return app
