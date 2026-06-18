# -*- coding: utf-8 -*-

# pylint: disable=unused-variable

import socket

from collections import defaultdict
from datetime import datetime
from random import randint
from io     import BytesIO
from quart  import Response, render_template, request, jsonify, send_from_directory, send_file, abort, url_for

import histodraw

from ifaces import Ifaces

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

        stats  = []
        ifaces = Ifaces()

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

            if ifaces.is_interface(target["addr"]):
                # no need to ping my own interfaces, ignore
                continue

            if target["local"] and not ifaces.is_local(target["addr"]):
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
        hostname   = socket.gethostname()
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

        # ── Layout constants ────────────────────────────────────────────────
        NODE_W      = 260
        H_GAP       = 70
        V_GAP       = 60
        PAD_X       = 80
        PAD_Y       = 86   # leaves room for 58px title bar + breathing space
        INNER_PAD   = 14
        TITLE_FONT  = 14
        BODY_FONT   = 11
        BODY_LINE_H = 17
        BODY_GAP    =  5

        STATE_COLORS = {
            "up":        "#22c55e",
            "different": "#f59e0b",
            "down":      "#ef4444",
            "self":      "#60a5fa",
            "dummy":     "#475569",
            "unknown":   "#475569",
        }

        def hop_height(hop):
            if not hop.get("address"):
                return 48
            body = 1  # address line always present
            if (hop.get("whois") or {}).get("asn"):
                body += 1
            if hop.get("target"):
                body += 1
            return INNER_PAD * 2 + TITLE_FONT + BODY_GAP + body * BODY_LINE_H

        SELF_H = INNER_PAD * 2 + TITLE_FONT + BODY_GAP + BODY_LINE_H

        # ── Build adjacency maps ────────────────────────────────────────────
        parents_of = defaultdict(list)
        for (lft, rgt) in uniq_links:
            parents_of[rgt].append(lft)

        # ── Group nodes by distance ─────────────────────────────────────────
        levels = defaultdict(list)
        levels[0] = ["SELF"]
        for hop_id, hop in uniq_hops.items():
            levels[hop["distance"]].append(hop_id)

        # ── Per-level max height and Y offsets ──────────────────────────────
        level_max_h = {0: SELF_H}
        for dist, hop_ids in levels.items():
            if dist == 0:
                continue
            level_max_h[dist] = max(hop_height(uniq_hops[hid]) for hid in hop_ids)

        level_y = {}
        y_cursor = PAD_Y
        for dist in sorted(levels.keys()):
            level_y[dist] = y_cursor
            y_cursor += level_max_h[dist] + V_GAP

        canvas_h = y_cursor - V_GAP + PAD_Y

        # ── Build spanning tree for column layout ────────────────────────────
        # Each node gets one primary parent (alphabetically first) that anchors
        # its column; all other parent→child links become extra DAG edges.
        # Sorting children alphabetically by hop_id gives a deterministic,
        # IP-address-ordered left-to-right arrangement.
        tree_children = defaultdict(list)
        for hid in uniq_hops:
            pars = sorted(parents_of.get(hid, []))
            if pars:
                tree_children[pars[0]].append(hid)
        for parent in list(tree_children):
            tree_children[parent].sort()

        # Assign each node a fractional leaf-index: leaves get integer slots,
        # internal nodes sit at the midpoint of their children's range.
        COL_W        = NODE_W + H_GAP
        leaf_counter = [0]
        x_col        = {}  # node_id -> fractional column index

        def assign_col(node):
            children = tree_children.get(node, [])
            if not children:
                x_col[node] = leaf_counter[0] + 0.5
                leaf_counter[0] += 1
            else:
                for child in children:
                    assign_col(child)
                x_col[node] = (x_col[children[0]] + x_col[children[-1]]) / 2

        assign_col("SELF")

        total_leaves = max(leaf_counter[0], 1)
        canvas_w     = max(1000, int(total_leaves * COL_W - H_GAP + 2 * PAD_X))
        tree_span    = total_leaves * COL_W - H_GAP
        col_offset   = PAD_X + (canvas_w - 2 * PAD_X - tree_span) / 2

        def col_to_px(col):
            return col_offset + col * COL_W

        # ── Assign pixel positions ───────────────────────────────────────────
        positions = {"SELF": (col_to_px(x_col["SELF"]), level_y[0] + SELF_H / 2)}
        for hid, hop in uniq_hops.items():
            if hid not in x_col:
                continue
            dist = hop["distance"]
            positions[hid] = (
                col_to_px(x_col[hid]),
                level_y[dist] + level_max_h[dist] / 2,
            )

        # ── Build edges with cubic-bezier control points ────────────────────
        def node_h(hid):
            if hid == "SELF":
                return SELF_H
            return hop_height(uniq_hops.get(hid, {}))

        edge_list = []
        for (lft, rgt) in sorted(uniq_links):
            if lft not in positions or rgt not in positions:
                continue
            sx, sy = positions[lft]
            tx, ty = positions[rgt]
            y1 = sy + node_h(lft) / 2
            y2 = ty - node_h(rgt) / 2
            dy = (y2 - y1) * 0.5
            edge_list.append({
                "x1": sx,  "y1": y1,
                "cx1": sx, "cy1": y1 + dy,
                "cx2": tx, "cy2": y2 - dy,
                "x2": tx,  "y2": y2,
            })

        # ── Compute AS group bounding boxes ─────────────────────────────────
        # Only groups with 2+ members get a border; single-hop ASes are noise.
        AS_PALETTE = [
            "#7c3aed", "#0891b2", "#d946ef", "#0d9488",
            "#9333ea", "#0284c7", "#c026d3", "#059669",
            "#6d28d9", "#0e7490",
        ]
        AS_PAD = 20  # padding around each AS group bounding box

        def as_color(asn):
            return AS_PALETTE[sum(ord(c) for c in str(asn)) % len(AS_PALETTE)]

        as_raw = defaultdict(lambda: {"name": "", "nodes": []})
        for hid, hop in uniq_hops.items():
            if hid not in positions:
                continue
            whois = hop.get("whois") or {}
            asn   = whois.get("asn")
            if not asn or asn == "NA":
                continue
            cx, cy = positions[hid]
            as_raw[asn]["name"] = (whois.get("network") or {}).get("name", "")
            as_raw[asn]["nodes"].append({"cx": cx, "cy": cy, "h": hop_height(hop)})

        as_group_list = []
        for asn, grp in sorted(as_raw.items()):
            if len(grp["nodes"]) < 2:
                continue
            color = as_color(asn)
            ns    = grp["nodes"]
            x0 = min(n["cx"] - NODE_W / 2 for n in ns) - AS_PAD
            y0 = min(n["cy"] - n["h"] / 2 for n in ns) - AS_PAD
            x1 = max(n["cx"] + NODE_W / 2 for n in ns) + AS_PAD
            y1 = max(n["cy"] + n["h"] / 2 for n in ns) + AS_PAD
            as_group_list.append({
                "asn":   str(asn),
                "name":  str(grp["name"])[:40],
                "color": color,
                "x0": x0, "y0": y0, "x1": x1, "y1": y1,
                "w":  x1 - x0, "h":  y1 - y0,
            })

        # ── Build node render list with pre-computed text lines ─────────────
        def make_lines(hop_id, hop, cx, cy, h, stroke):
            top    = cy - h / 2
            lx     = cx - NODE_W / 2 + 16   # left text margin
            title_y = top + INNER_PAD + TITLE_FONT
            body_y0 = title_y + BODY_GAP + BODY_LINE_H

            if hop_id == "SELF":
                return [
                    dict(text=hostname[:30],  href=None, x=lx,  y=title_y,
                         size=TITLE_FONT, weight="600",    fill="#f1f5f9", anchor="start"),
                    dict(text="This node",    href=None, x=lx,  y=body_y0,
                         size=BODY_FONT,  weight="normal", fill="#64748b", anchor="start"),
                ]

            if not hop.get("address"):
                return [
                    dict(text="?", href=None, x=cx, y=cy + TITLE_FONT * 0.35,
                         size=TITLE_FONT + 4, weight="600", fill="#64748b", anchor="middle"),
                ]

            name = (hop.get("target") and hop["target"].name) or hop.get("name") or hop["address"]
            lines = [
                dict(text=name[:30], href=None, x=lx, y=title_y,
                     size=TITLE_FONT, weight="600", fill="#f1f5f9", anchor="start"),
            ]

            addr = hop["address"]
            body_y = body_y0
            lines.append(dict(
                text=addr, href="https://ipinfo.io/" + addr,
                x=lx, y=body_y, size=BODY_FONT, weight="normal", fill="#94a3b8", anchor="start",
            ))
            body_y += BODY_LINE_H

            whois = hop.get("whois") or {}
            if whois.get("asn"):
                net_name = (whois.get("network") or {}).get("name", "")
                text     = ("AS" + str(whois["asn"]) + ": " + net_name)[:34]
                lines.append(dict(
                    text=text, href="https://bgp.tools/as/" + str(whois["asn"]),
                    x=lx, y=body_y, size=BODY_FONT, weight="normal", fill="#64748b", anchor="start",
                ))
                body_y += BODY_LINE_H

            if hop.get("target"):
                tgt_url = url_for("histogram", node=hostname, target=hop["target"].addr, _external=True)
                lines.append(dict(
                    text="View Histogram →", href=tgt_url,
                    x=lx, y=body_y, size=BODY_FONT, weight="normal", fill=stroke, anchor="start",
                ))

            return lines

        node_list = []

        cx0, cy0 = positions["SELF"]
        stroke0   = STATE_COLORS["self"]
        node_list.append({
            "cx": cx0, "cy": cy0, "w": NODE_W, "h": SELF_H,
            "state": "self", "stroke": stroke0,
            "lines": make_lines("SELF", {}, cx0, cy0, SELF_H, stroke0),
        })

        for hid, hop in uniq_hops.items():
            if hid not in positions:
                continue
            cx, cy  = positions[hid]
            h       = hop_height(hop)
            state   = "dummy" if not hop.get("address") else hop.get("state", "unknown")
            stroke  = STATE_COLORS.get(state, "#475569")
            node_list.append({
                "cx": cx, "cy": cy, "w": NODE_W, "h": h,
                "state": state, "stroke": stroke,
                "lines": make_lines(hid, hop, cx, cy, h, stroke),
            })

        now = datetime.now()

        tpl = await render_template(
            "network.svg",
            hostname  = hostname,
            now       = now.strftime("%Y-%m-%d %H:%M:%S"),
            canvas_w  = int(canvas_w),
            canvas_h  = int(canvas_h),
            nodes     = node_list,
            edges     = edge_list,
            as_groups = as_group_list,
        )

        resp = Response(tpl, mimetype="image/svg+xml")
        resp.headers["refresh"]             = "43200"
        resp.headers["Cache-Control"]       = "max-age=36000, public"
        resp.headers["content-disposition"] = (
            'inline; filename="meshping_%s_network.svg"' % now.strftime("%Y-%m-%d_%H-%M-%S")
        )
        return resp
