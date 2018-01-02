# -*- coding: utf-8 -*-

from uuid import uuid4
from operator import itemgetter
from flask import Flask, Response


def run_prom(mp):
    app = Flask(__name__)

    @app.route("/")
    def hai():

        targets = [
            "Target                    Address                    Sent  Recv   Succ    Loss      Min       Avg       Max      Last"
        ]

        def ip_as_int(tgt):
            import socket
            import struct
            if tgt["af"] == socket.AF_INET:
                return struct.unpack("!I", socket.inet_aton( tgt["addr"] ))[0]
            elif tgt["af"] == socket.AF_INET6:
                ret = 0
                for intpart in struct.unpack("!IIII", socket.inet_pton(socket.AF_INET6, tgt["addr"] )):
                    ret = ret<<32 | intpart
                return ret

        for targetinfo in sorted(mp.targets.values(), key=ip_as_int):
            loss = 0
            errs = 0
            if targetinfo["sent"]:
                loss = (targetinfo["sent"] - targetinfo["recv"]) / targetinfo["sent"] * 100
            avg = 0
            if targetinfo["recv"]:
                avg = targetinfo["sum"] / targetinfo["recv"]
            outd = 0
            targets.append(
                """%(name)-25s %(addr)-25s %(sent)5d %(recv)5d %(succ)6.2f%% %(loss)6.2f%% %(min)7.2f   %(avg)7.2f   %(max)7.2f   %(last)7.2f    <a href="/histogram/%(addr)-25s">H</a>""" % dict(
                    targetinfo,
                    succ=100 - loss,
                    loss=loss,
                    avg=avg
                )
            )

        return Response(''.join([
            """<h1>Meshping</h1>""",
            """<a href="/metrics">metrics</a>""",
            """<pre style="white-space: pre-wrap">%s</pre>""" % '\n'.join(targets),
        ]))

    @app.route("/histogram/<addr>")
    def histogram(addr):
        base = 2
        bukkits = []
        histogram = mp.histograms.get(addr, {})

        # Let's try a modality detection
        # http://www.brendangregg.com/FrequencyTrails/modes.html
        last    = None
        mvalue  = 0
        maxnum  = None

        for bktval, count in sorted(histogram.items(), key=itemgetter(0), reverse=True):
            bukkits.append("%7.2f - %7.2f -> %5d %s" % ( base ** (bktval / 10.), base ** ((bktval + 1) / 10.), count, (u"■".encode("utf-8")) * count ))
            if last is not None:
                mvalue += abs(count - last)
                maxnum  = max(maxnum, count)
            last = count

        if maxnum is not None:
            mvalue /= maxnum
            bukkits.append("%d buckets, mvalue=%.2f (probably %s multimodal)" % (len(histogram), mvalue, "is" if mvalue > 2.4 else "not"))

        return Response(''.join([
            """<h1>Meshping: %s</h1>""" % addr.encode("utf-8"),
            """<pre style="white-space: pre-wrap">%s</pre>""" % '\n'.join(bukkits),
        ]))


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
                'meshping_sent{target="%(addr)s"} %(sent)d',

                'meshping_recv{target="%(addr)s"} %(recv)d',

                'meshping_lost{target="%(addr)s"} %(lost)d',
            ]) % target)

            if target["recv"]:
                target = dict(target, avg=(target["sum"] / target["recv"]))
                respdata.append('\n'.join([
                    'meshping_max{target="%(addr)s"} %(max).2f',

                    'meshping_min{target="%(addr)s"} %(min).2f',
                ]) % target)

            respdata.append('\n'.join([
                'meshping_pings_sum{target="%(addr)s"} %(sum)f',
                'meshping_pings_count{target="%(addr)s"} %(recv)d',
            ]) % target)

            histogram = mp.histograms.get(addr, {})
            buckets = sorted(histogram.keys(), key=float)
            count = 0
            for bucket in buckets:
                nextping = 2 ** ((bucket + 1) / 10.) - 0.01
                count += histogram[bucket]
                respdata.append('meshping_pings_bucket{target="%(addr)s",le="%(le).2f"} %(count)d' % dict(
                    addr  = addr,
                    count = count,
                    le    = nextping
                ))

        return Response('\n'.join(respdata) + '\n', mimetype="text/plain")



    app.secret_key = str(uuid4())
    app.debug = False

    app.run(host="::", port=9922)
