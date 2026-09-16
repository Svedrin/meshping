# -*- coding: utf-8 -*-

# pylint: disable=unused-variable

import json
import socket

from collections import defaultdict
from datetime import datetime
from random import randint
from io     import BytesIO
from quart  import Response, render_template, request, jsonify, send_from_directory, send_file, abort, url_for

import histodraw

from ifaces import Ifaces

# ── /network.svg: transit-map layout ─────────────────────────────────────
#
# Every monitored target's traceroute is a root-to-leaf path out of SELF.
# Instead of drawing each hop as its own row in a dendrogram (which turns
# any host with a wide fan-out into an equally wide page), we treat each
# such path as a *line*: lines run together while hops are shared, and peel
# off at a 45-degree junction only where routes actually diverge. Only the
# local host, real branch points, destinations, and provider (AS) boundary
# crossings get a name card; a plain pass-through hop is a small dot you
# hover for its hostname/IP - the way a subway map doesn't name every
# signal box between stations.
#
# The layout math here is mirrored in the client-side JS embedded in the
# network.svg template, so collapsing a branch can recompute lanes and
# junctions without a round-trip to the server (and the saved/downloaded
# SVG keeps working offline, same as the old collapse/expand code did).

LANE_H        = 60    # vertical px between adjacent lines/stations
HOP_STEP      = 58    # minimum horizontal px per traceroute hop
JUNCTION_PAD  = 30    # extra slack added to a fanning-out column's width
PAD_X         = 110
PAD_Y         = 86    # clears the 58px title bar
BOTTOM_PAD    = 40
LABEL_ROOM    = 300   # right-hand room for the widest terminus label
CANVAS_W_MIN  = 760
CANVAS_H_MIN  = 360

STATE_COLORS = {
    "different": "#f59e0b",
    "down":      "#ef4444",
}

# The dataviz-validated 8-hue categorical set (dark-surface steps). Branches
# keep their parent line's colour when they fork - like the Northern line
# staying black across its Bank and Charing Cross branches - so running out
# of hues only becomes a problem past 8 *independent* first hops out of
# SELF, at which point we start stepping the palette lighter/darker instead
# of inventing new hues.
LINE_PALETTE = [
    "#3987e5", "#d95926", "#199e70", "#c98500",
    "#d55181", "#1fae1f", "#9085e9", "#e66767",
]

def _shade(hexcolor, amount):
    # amount > 0 lightens toward white, < 0 darkens toward black
    r, g, b = int(hexcolor[1:3], 16), int(hexcolor[3:5], 16), int(hexcolor[5:7], 16)
    target = 255 if amount > 0 else 0
    f = abs(amount)
    r, g, b = (max(0, min(255, int(c + (target - c) * f))) for c in (r, g, b))
    return "#%02x%02x%02x" % (r, g, b)

def _line_color(index):
    bank, slot = divmod(index, len(LINE_PALETTE))
    base = LINE_PALETTE[slot]
    if bank == 0:
        return base
    return _shade(base, 0.22 * ((bank + 1) // 2) * (1 if bank % 2 else -1))

def _display_name(hop):
    return (hop.get("target") and hop["target"].name) or hop.get("name") or hop.get("address") or "?"

def _asn_of(hop):
    if not hop:
        return None
    return (hop.get("whois") or {}).get("asn")

def _elbow_path(x1, y1, x2, y2):
    dy = y2 - y1
    if abs(dy) < 0.01:
        return "M%.2f,%.2f L%.2f,%.2f" % (x1, y1, x2, y2)
    run = min(abs(dy), x2 - x1)
    xa  = x2 - run
    return "M%.2f,%.2f L%.2f,%.2f L%.2f,%.2f" % (x1, y1, xa, y1, x2, y2)

async def render_network_svg(hostname, uniq_hops, uniq_links):
    # ── adjacency ──────────────────────────────────────────────────────
    parents_of = defaultdict(list)
    for (lft, rgt) in uniq_links:
        parents_of[rgt].append(lft)

    # Primary spanning tree: each node's lane is anchored to its
    # alphabetically-first parent; any other parent->child link becomes an
    # "extra" edge (two lines converging on a shared hop), still drawn but
    # not used for lane assignment. Sorting children alphabetically by
    # hop_id gives a deterministic, IP-address-ordered arrangement.
    tree_children = defaultdict(list)
    for hid in uniq_hops:
        pars = sorted(parents_of.get(hid, []))
        if pars:
            tree_children[pars[0]].append(hid)
    for parent in list(tree_children):
        tree_children[parent].sort()

    # ── lanes: one vertical slot per terminus, internal nodes sit at the
    # midpoint of their children's range ─────────────────────────────────
    lane = {}
    leaf_counter = [0]
    def assign_lane(node):
        kids = tree_children.get(node, [])
        if not kids:
            lane[node] = float(leaf_counter[0])
            leaf_counter[0] += 1
        else:
            for kid in kids:
                assign_lane(kid)
            lane[node] = (lane[kids[0]] + lane[kids[-1]]) / 2
    assign_lane("SELF")
    total_leaves = max(leaf_counter[0], 1)

    # Descendant counts (for the "N hidden" badge shown on a collapsed node)
    descendant_count = {}
    def count_descendants(node):
        if node in descendant_count:
            return descendant_count[node]
        total = 0
        for kid in tree_children.get(node, []):
            total += 1 + count_descendants(kid)
        descendant_count[node] = total
        return total
    count_descendants("SELF")

    # ── which line (top-level branch out of SELF) owns each node ────────
    top_order = list(tree_children.get("SELF", []))
    line_of = {"SELF": "SELF"}
    def paint(node, top):
        line_of[node] = top
        for kid in tree_children.get(node, []):
            paint(kid, top)
    for top in top_order:
        paint(top, top)
    line_index = {top: i for i, top in enumerate(top_order)}

    def edge_owner(lft, rgt):
        owner = line_of.get(lft)
        if owner is None or owner == "SELF":
            owner = line_of.get(rgt)
        return owner

    def count_leaves(node):
        kids = tree_children.get(node, [])
        if not kids:
            return 1
        return sum(count_leaves(kid) for kid in kids)

    # ── legend: one row per line, plus a compact status key. Computed here
    # (rather than after positions/canvas size) because canvas_h needs
    # legend_h to guarantee the legend panel never overlaps the last row
    # of station labels on a small map. ──────────────────────────────────
    def _truncate(text, n):
        return text if len(text) <= n else text[:n - 1] + "…"

    legend_lines = []
    for i, top in enumerate(top_order):
        top_hop = uniq_hops.get(top, {})
        legend_lines.append({
            "color": _line_color(i),
            "name": _truncate(_display_name(top_hop), 19) if top_hop.get("address") else "?",
            "count": count_leaves(top),
        })
    # Must track the geometry baked into the legend block in network.svg:
    # a "LINES" header, one 20px row per line, then a 3-row status key.
    legend_h = 96 + len(legend_lines) * 20

    # ── depth (hop count from SELF) and per-level column width ──────────
    depth_of = {"SELF": 0}
    for hid, hop in uniq_hops.items():
        depth_of[hid] = hop["distance"]
    max_depth = max(depth_of.values()) if uniq_hops else 0

    level_min_w = defaultdict(lambda: HOP_STEP)
    for (lft, rgt) in uniq_links:
        if lft not in lane or rgt not in lane:
            continue
        d  = depth_of.get(lft, 0)
        dy = abs(lane[rgt] - lane[lft]) * LANE_H
        if dy > level_min_w[d] - JUNCTION_PAD:
            level_min_w[d] = dy + JUNCTION_PAD

    x_at_depth = [0.0] * (max_depth + 2)
    x_at_depth[0] = PAD_X
    for d in range(max_depth + 1):
        x_at_depth[d + 1] = x_at_depth[d] + level_min_w[d]

    positions = {}
    for nid in lane:
        d = depth_of.get(nid, 0)
        positions[nid] = (x_at_depth[d], PAD_Y + lane[nid] * LANE_H)

    canvas_w = max(CANVAS_W_MIN, int(x_at_depth[max_depth + 1] + LABEL_ROOM))
    # The legend panel is anchored to the bottom of the canvas, so its
    # height has to be part of this sum - otherwise a map with only a
    # handful of termini can end up with the legend overlapping the last
    # row's label (a leaf's 3rd text line runs ~24px below its centre).
    last_row_clearance = 24
    content_h = PAD_Y + (total_leaves - 1) * LANE_H + last_row_clearance + legend_h + BOTTOM_PAD
    canvas_h  = max(CANVAS_H_MIN, int(content_h))

    # ── station classification ───────────────────────────────────────────
    # root: SELF. interchange: a path forks (>=2 onward hops). leaf: a
    # terminus (a monitored target, or the last hop a trace reached).
    # landmark: a plain pass-through hop where the AS changes underneath it
    # (crossing into a different network - worth a name). minor: every
    # other pass-through hop; a small tick with a hover tooltip. A hop that
    # is currently down or shows a changed route is always promoted to at
    # least landmark visibility, so a real problem never hides as an
    # anonymous dot.
    kind = {"SELF": "root"}
    for hid, hop in uniq_hops.items():
        kids = tree_children.get(hid, [])
        if not kids:
            k = "leaf"
        elif len(kids) >= 2:
            k = "interchange"
        else:
            pid   = (sorted(parents_of.get(hid, [])) or [None])[0]
            p_hop = uniq_hops.get(pid) if pid and pid != "SELF" else None
            this_asn = _asn_of(hop)
            k = "landmark" if (this_asn and this_asn != _asn_of(p_hop)) else "minor"
        if hop.get("state") in ("down", "different") and k == "minor":
            k = "landmark"
        kind[hid] = k

    # ── edges ─────────────────────────────────────────────────────────
    edge_list = []
    for (lft, rgt) in sorted(uniq_links):
        if lft not in positions or rgt not in positions:
            continue
        x1, y1 = positions[lft]
        x2, y2 = positions[rgt]
        color  = _line_color(line_index.get(edge_owner(lft, rgt), 0))
        weight = descendant_count.get(rgt, 0)
        edge_list.append({
            "src": lft, "tgt": rgt,
            "d": _elbow_path(x1, y1, x2, y2),
            "color": color,
            "width": round(max(2.0, min(8.0, 2.0 + weight * 0.4)), 2),
            "dummy": not uniq_hops.get(rgt, {}).get("address"),
        })

    # ── stations ──────────────────────────────────────────────────────
    def href_ipinfo(addr):
        return "https://ipinfo.io/" + addr

    def href_bgp(asn):
        return "https://bgp.tools/as/" + str(asn)

    node_list = []
    cx, cy = positions["SELF"]
    node_list.append({
        "id": "SELF", "cx": cx, "cy": cy, "kind": "root",
        "color": "#8aa0c0", "dummy": False, "state": None,
        "has_collapse": bool(tree_children.get("SELF")),
        "descendants": descendant_count.get("SELF", 0),
        "name": hostname[:30], "addr": None, "addr_href": None,
        "asn_text": None, "asn_href": None, "hist_href": None,
        "extra_text": "this node", "title": hostname,
    })

    # landmark labels alternate above/below within their own lane, so two
    # landmarks a couple of hops apart on the same line don't collide
    landmark_side = {}

    for hid, hop in uniq_hops.items():
        if hid not in positions:
            continue
        cx, cy  = positions[hid]
        k       = kind[hid]
        color   = _line_color(line_index.get(line_of.get(hid), 0))
        dummy   = not hop.get("address")
        state   = None if dummy else hop.get("state")
        node = {
            "id": hid, "cx": cx, "cy": cy, "kind": k,
            "color": color, "dummy": dummy, "state": state,
            "state_color": STATE_COLORS.get(state),
            "has_collapse": k in ("root", "interchange") and bool(tree_children.get(hid)),
            "descendants": descendant_count.get(hid, 0),
            "name": None, "addr": None, "addr_href": None,
            "asn_text": None, "asn_href": None, "hist_href": None,
            "extra_text": None, "title": "no response",
            "label_above": True,
        }

        if not dummy:
            addr  = hop["address"]
            name  = _display_name(hop)[:30]
            asn   = _asn_of(hop)
            whois = hop.get("whois") or {}
            title = name if name != addr else addr
            if addr != name:
                title += " — " + addr

            node.update(name=name, addr=addr, addr_href=href_ipinfo(addr))

            if asn:
                net_name = (whois.get("network") or {}).get("name", "")
                node.update(
                    asn_text=("AS%s: %s" % (asn, net_name))[:34],
                    asn_href=href_bgp(asn),
                )
                title += " (AS%s %s)" % (asn, net_name)
                if k == "landmark":
                    short = (net_name.split("-")[0] if net_name else str(asn))[:14]
                    node["extra_text"] = "AS%s %s" % (asn, short)
                    lane_key = round(lane[hid], 2)
                    landmark_side[lane_key] = not landmark_side.get(lane_key, False)
                    node["label_above"] = landmark_side[lane_key]

            if hop.get("target"):
                node["hist_href"] = url_for("histogram", node=hostname, target=hop["target"].addr, _external=True)

            if k == "interchange":
                node["extra_text"] = "AS%s · splits %d ways" % (asn, len(tree_children[hid])) if asn \
                    else "splits %d ways" % len(tree_children[hid])

            if state in ("down", "different"):
                title += " - " + state
            node["title"] = title

        node_list.append(node)

    layout_data = {
        "tree":  {nid: tree_children.get(nid, []) for nid in lane},
        "depth": depth_of,
        "links": [[lft, rgt] for (lft, rgt) in uniq_links if lft in lane and rgt in lane],
        "laneH": LANE_H, "hopStep": HOP_STEP, "junctionPad": JUNCTION_PAD,
        "padX": PAD_X, "padY": PAD_Y, "bottomPad": BOTTOM_PAD, "labelRoom": LABEL_ROOM,
        "canvasWMin": CANVAS_W_MIN, "canvasHMin": CANVAS_H_MIN,
        "legendH": legend_h,
    }

    now = datetime.now()

    tpl = await render_template(
        "network.svg",
        hostname     = hostname,
        now          = now.strftime("%Y-%m-%d %H:%M:%S"),
        canvas_w     = canvas_w,
        canvas_h     = canvas_h,
        nodes        = node_list,
        edges        = edge_list,
        legend_lines = legend_lines,
        legend_h     = legend_h,
        n_stations   = len(node_list),
        layout_json  = json.dumps(layout_data),
    )
    return tpl, now

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

        tpl, now = await render_network_svg(hostname, uniq_hops, uniq_links)

        resp = Response(tpl, mimetype="image/svg+xml")
        resp.headers["refresh"]             = "43200"
        resp.headers["Cache-Control"]       = "max-age=36000, public"
        resp.headers["content-disposition"] = (
            'inline; filename="meshping_%s_network.svg"' % now.strftime("%Y-%m-%d_%H-%M-%S")
        )
        return resp
