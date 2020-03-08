# -*- coding: utf-8 -*-

from __future__ import division

from uuid  import uuid4
from flask import Flask, Response, render_template

def run_prom(mp):
    app = Flask(__name__)

    @app.route("/")
    def hai():

        targets = []

        def ip_as_int(tgt):
            import socket
            import struct
            if ":" not in tgt["addr"]:
                return struct.unpack("!I", socket.inet_aton( tgt["addr"] ))[0]
            else:
                ret = 0
                for intpart in struct.unpack("!IIII", socket.inet_pton(socket.AF_INET6, tgt["addr"] )):
                    ret = ret<<32 | intpart
                return ret

        for targetinfo in sorted(mp.targets.values(), key=ip_as_int):
            loss = 0
            if targetinfo["sent"]:
                loss = (targetinfo["sent"] - targetinfo["recv"]) / targetinfo["sent"] * 100
            targets.append(
                dict(
                    targetinfo,
                    name=targetinfo["name"][:24],
                    succ=100 - loss,
                    loss=loss,
                    avg15m=targetinfo.get("avg15m", 0),
                    avg6h =targetinfo.get("avg6h",  0),
                    avg24h=targetinfo.get("avg24h", 0),
                )
            )

        return render_template("index.html", Targets=targets)

    @app.route("/metrics")
    def metrics():
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

    app.secret_key = str(uuid4())
    app.debug = False

    app.run(host="::", port=9922)
