from uuid import uuid4
from flask import Flask, Response


def run_prom(mp):
    app = Flask(__name__)

    @app.route("/")
    def hai():
        return Response("""<h1>Meshping</h1><a href="/metrics">metrics</a>""")

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
            '# HELP meshping_avg avg ping',
            '# TYPE meshping_avg gauge',
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

                    'meshping_avg{target="%(addr)s"} %(avg).2f',
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
