# -*- coding: utf-8 -*-

# pylint: disable=unused-variable

import socket

from subprocess import run as run_command
from datetime import datetime
from random import randint
from io     import BytesIO
from quart  import Response, render_template, request, jsonify, send_from_directory, send_file, abort

import histodraw

from ifaces import Ifaces4

def add_api_views(app, mp):
    @app.route("/")
    async def index():
        return await render_template(
            "index.html",
            Hostname=socket.gethostname(),
        )

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

        for target in mp.all_targets():
            target_info = dict(
                target.statistics,
                addr = target.addr,
                name = target.name
            )
            respdata.append('\n'.join([
                'meshping_sent{name="%(name)s",target="%(addr)s"} %(sent)d',
                'meshping_recv{name="%(name)s",target="%(addr)s"} %(recv)d',
                'meshping_lost{name="%(name)s",target="%(addr)s"} %(lost)d',
            ]) % target_info)

            if target_info["recv"]:
                respdata.append('\n'.join([
                    'meshping_max{name="%(name)s",target="%(addr)s"} %(max).2f',
                    'meshping_min{name="%(name)s",target="%(addr)s"} %(min).2f',
                ]) % target_info)

            respdata.append('\n'.join([
                'meshping_pings_sum{name="%(name)s",target="%(addr)s"} %(sum)f',
                'meshping_pings_count{name="%(name)s",target="%(addr)s"} %(recv)d',
            ]) % target_info)

            histogram = target.histogram.tail(1)
            count = 0
            for bucket in histogram.columns:
                if histogram[bucket][0] == 0:
                    continue
                nextping = 2 ** ((bucket + 1) / 10.)
                count += histogram[bucket][0]
                respdata.append(
                    'meshping_pings_bucket{name="%(name)s",target="%(addr)s",le="%(le).2f"} %(count)d' % dict(
                        addr  = target.addr,
                        count = count,
                        le    = nextping,
                        name  = target.name,
                    )
                )
            respdata.append(
                'meshping_pings_bucket{name="%(name)s",target="%(addr)s",le="+Inf"} %(count)d' % dict(
                    addr  = target.addr,
                    count = count,
                    name  = target.name,
                )
            )

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

        if not isinstance(request_json.get("targets"), list):
            return "need targets as a list", 400

        stats = []
        if4   = Ifaces4()

        for target in request_json["targets"]:
            if not isinstance(target, dict):
                return "targets must be dicts", 400
            if (
                not target.get("name", "").strip() or
                not target.get("addr", "").strip() or
                not isinstance(target.get("local"), bool)
            ):
                return "required field missing in target", 400

            target["name"] = target["name"].strip()
            target["addr"] = target["addr"].strip()

            if if4.is_interface(target["addr"]):
                # no need to ping my own interfaces, ignore
                continue

            if target["local"] and not if4.is_local(target["addr"]):
                continue

            # See if we know this target already, otherwise create it.
            try:
                target = mp.get_target(target["addr"])
            except LookupError:
                target_str = "%(name)s@%(addr)s" % target
                mp.add_target(target_str)
                target = mp.get_target(target["addr"])
                target.set_is_foreign(True)
            stats.append(target.statistics)

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

    @app.route("/api/resolve/<name>")
    async def resolve(name):
        try:
            return jsonify(success=True, addrs=[
                info[4][0]
                for info in socket.getaddrinfo(name, 0, 0, socket.SOCK_STREAM)
            ])
        except socket.gaierror as err:
            return jsonify(success=False, error=str(err))

    @app.route("/api/targets", methods=["GET", "POST"])
    async def targets():
        if request.method == "GET":
            targets = []

            for target in mp.all_targets():
                target_stats = target.statistics
                succ = 0
                loss = 0
                if target_stats["sent"] > 0:
                    succ = target_stats["recv"] / target_stats["sent"] * 100
                    loss = (target_stats["sent"] - target_stats["recv"]) / target_stats["sent"] * 100
                targets.append(
                    dict(
                        target_stats,
                        addr=target.addr,
                        name=target.name,
                        state=target.state,
                        error=target.error,
                        succ=succ,
                        loss=loss,
                        traceroute=target.traceroute,
                        route_loop=target.route_loop,
                    )
                )

            return jsonify(success=True, targets=targets)

        if request.method == "POST":
            request_json = await request.get_json()
            if "target" not in request_json:
                return "missing target", 400

            target = request_json["target"]
            added = []

            if "@" not in target:
                try:
                    addrinfo = socket.getaddrinfo(target, 0, 0, socket.SOCK_STREAM)
                except socket.gaierror as err:
                    return jsonify(success=False, target=target, error=str(err))

                for info in addrinfo:
                    target_with_addr = "%s@%s" % (target, info[4][0])
                    mp.add_target(target_with_addr)
                    added.append(target_with_addr)
            else:
                mp.add_target(target)
                added.append(target)

            return jsonify(success=True, targets=added)

        abort(400)

    @app.route("/api/targets/<target>", methods=["PATCH", "PUT", "DELETE"])
    async def edit_target(target):
        if request.method == "DELETE":
            mp.remove_target(target)
            return jsonify(success=True)

        return jsonify(success=False)

    @app.route("/api/stats", methods=["DELETE"])
    async def clear_statistics():
        mp.clear_statistics()
        return jsonify(success=True)

    @app.route("/histogram/<node>/<target>.png")
    async def histogram(node, target):
        targets = []
        for arg_target in [target] + request.args.getlist("compare"):
            try:
                targets.append(mp.get_target(arg_target))
            except LookupError:
                print("lookuperror")
                abort(404, description=f"Target {arg_target} not found")

        if len(targets) > 3:
            # an RGB image only has three channels
            abort(400, description="Can only compare up to three targets")

        try:
            img = histodraw.render(targets, mp.histogram_period)
        except ValueError as err:
            abort(404, description=err)

        img_io = BytesIO()
        img.save(img_io, 'png')
        length = img_io.tell()
        img_io.seek(0)

        resp = await send_file(img_io, mimetype='image/png')
        resp.headers["content-length"] = length
        resp.headers["refresh"] = "300"
        resp.headers["content-disposition"] = (
            'inline; filename="meshping_%s_%s.png"' % (
                datetime.now().strftime("%Y-%m-%d_%H-%M-%S"),
                target
            )
        )

        return resp

    @app.route("/network.svg")
    async def network_diagram():
        targets    = mp.all_targets()
        uniq_hops  = {}
        uniq_links = set()

        for target in targets:
            prev_hop  = "SELF"
            prev_dist = 0
            for hop in target.traceroute:
                hop_id = hop["address"].replace(":", "_").replace(".", "_")

                # Check if we know this hop already. If we do, just skip ahead.
                if hop_id not in uniq_hops:
                    # Fill in the blanks for missing hops, if any
                    while hop["distance"] > prev_dist + 1:
                        dummy_id = str(randint(10000000, 99999999))
                        dummy = dict(id=dummy_id, distance=(prev_dist + 1), address=None, name=None, target=None, whois=None)
                        uniq_hops[dummy_id] = dummy
                        uniq_links.add( (prev_hop, dummy_id) )
                        prev_hop   = dummy_id
                        prev_dist += 1

                    # Now render the hop itself
                    hop_id = hop["address"].replace(":", "_").replace(".", "_")
                    uniq_hops.setdefault(hop_id, dict(hop, id=hop_id, target=None))
                    uniq_links.add( (prev_hop, hop_id) )

                    # make sure we show the most recent state info
                    if (
                        uniq_hops[hop_id]["state"] != hop["state"] and
                        uniq_hops[hop_id]["time"]  <  hop["time"]
                    ):
                        uniq_hops[hop_id].update(state=hop["state"], time=hop["time"])

                if hop["address"] == target.addr:
                    uniq_hops[hop_id]["target"] = target

                prev_hop  = hop_id
                prev_dist = hop["distance"]


        now = datetime.now()

        tpl = await render_template(
            "network.puml",
            hostname   = socket.gethostname(),
            now        = now.strftime("%Y-%m-%d %H:%M:%S"),
            targets    = targets,
            uniq_hops  = uniq_hops,
            uniq_links = sorted(uniq_links),
            uniq_hops_sorted = [uniq_hops[hop] for hop in sorted(uniq_hops.keys())],
        );

        plantuml = run_command(["plantuml", "-tsvg", "-p"], input=tpl.encode("utf-8"), capture_output=True)

        if plantuml.stderr:
            return Response(plantuml.stderr.decode("utf-8") + "\n\n===\n\n" + tpl, mimetype="text/plain"), 500

        resp = Response(
            plantuml.stdout,
            mimetype="image/svg+xml"
        )

        resp.headers["refresh"]       = "43200"                 # 12h
        resp.headers["Cache-Control"] = "max-age=36000, public" # 10h

        resp.headers["content-disposition"] = (
            'inline; filename="meshping_%s_network.svg"' % (
                now.strftime("%Y-%m-%d_%H-%M-%S")
            )
        )

        return resp
