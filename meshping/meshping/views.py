# We cannot rename view parameters as django spllies them as keyword arguments, so:
# pylint: disable=unused-argument

import json
import os
import socket
from datetime import datetime
from random import randint
from subprocess import run as run_command

from django.forms.models import model_to_dict
from django.http import (
    HttpResponse,
    HttpResponseBadRequest,
    HttpResponseNotFound,
    HttpResponseServerError,
    JsonResponse,
)
from django.template import loader
from django.views.decorators.http import require_http_methods
from markupsafe import Markup

from .meshping.ifaces import Ifaces4
from .meshping import histodraw
from .models import (
    Statistics,
    Target,
    TargetState,
    Meta,
    target_histograms,
    target_traceroute,
)


# TODO remove business logic in this file


# route /
# TODO do not load icons from disk for every request
# TODO find a better method for finding the icons to not have an absolute path here
# TODO make local development possible when node modules are on disk (relative path)
@require_http_methods(["GET"])
def index(request):
    def read_svg_file(icons_dir, filename):
        with open(os.path.join(icons_dir, filename), "r", encoding="utf-8") as f:
            return Markup(f.read())

    template = loader.get_template("index.html.j2")
    # icons_dir = "/opt/meshping/ui/node_modules/bootstrap-icons/icons/"
    icons_dir = "../ui/node_modules/bootstrap-icons/icons/"
    icons_dir = os.path.join(os.path.dirname(__file__), icons_dir)
    icons = {
        filename: read_svg_file(icons_dir, filename)
        for filename in os.listdir(icons_dir)
    }
    context = {
        "Hostname": socket.gethostname(),
        "icons": icons,
    }
    return HttpResponse(template.render(context, request))


# route /histogram/<str:node>/<str:target>.png
#
# we cannot rename node to _node as django calls by keyword argument, so ignore this
# pylint: disable=unused-argument
@require_http_methods(["GET"])
def histogram(request, node, target):
    targets = []
    for arg_target in [target] + request.GET.getlist("compare", default=None):
        try:
            targets.append(Target.objects.get(addr=arg_target))
        except Target.DoesNotExist:
            return HttpResponseNotFound(f"Target {arg_target} not found")

    if len(targets) > 3:
        # an RGB image only has three channels
        return HttpResponseBadRequest("Can only compare up to three targets")

    try:
        # TODO reference the configuration, with the current setup there is no
        #      obvious clean way (at least to me)
        img = histodraw.render(targets, 3 * 24 * 3600)
    except ValueError as err:
        return HttpResponseNotFound(str(err))

    response = HttpResponse(content_type="image/png")
    img.save(response, "png")
    response["refresh"] = "300"
    response["content-disposition"] = (
        'inline; filename="meshping_'
        f'{datetime.now().strftime("%Y-%m-%d_%H-%M-%S")}_{target}.png"'
    )
    return response


# route /metrics
@require_http_methods(["GET"])
def metrics(request):
    respdata = [
        "\n".join(
            [
                "# HELP meshping_sent Sent pings",
                "# TYPE meshping_sent counter",
                "# HELP meshping_recv Received pongs",
                "# TYPE meshping_recv counter",
                "# HELP meshping_lost Lost pings (actual counter, not just sent-recv)",
                "# TYPE meshping_lost counter",
                "# HELP meshping_max max ping",
                "# TYPE meshping_max gauge",
                "# HELP meshping_min min ping",
                "# TYPE meshping_min gauge",
                "# HELP meshping_pings Pings bucketed by response time",
                "# TYPE meshping_pings histogram",
            ]
        )
    ]

    for target in Target.objects.all():
        target_stats, _created = Statistics.objects.get_or_create(target=target)
        target_info = dict(
            model_to_dict(target_stats), addr=target.addr, name=target.name
        )
        respdata.append(
            "\n".join(
                [
                    'meshping_sent{name="%(name)s",target="%(addr)s"} %(sent)d',
                    'meshping_recv{name="%(name)s",target="%(addr)s"} %(recv)d',
                    'meshping_lost{name="%(name)s",target="%(addr)s"} %(lost)d',
                ]
            )
            % target_info
        )

        if target_info["recv"]:
            respdata.append(
                "\n".join(
                    [
                        'meshping_max{name="%(name)s",target="%(addr)s"} %(max).2f',
                        'meshping_min{name="%(name)s",target="%(addr)s"} %(min).2f',
                    ]
                )
                % target_info
            )

        respdata.append(
            "\n".join(
                [
                    'meshping_pings_sum{name="%(name)s",target="%(addr)s"} %(sum)f',
                    'meshping_pings_count{name="%(name)s",target="%(addr)s"} %(recv)d',
                ]
            )
            % target_info
        )

        # TODO error handling if there is no line in the result
        hist = target_histograms(target)[-1]
        count = 0
        for bucket in hist.keys():
            if bucket == "timestamp":
                continue
            if not hist[bucket]:
                continue
            nextping = 2 ** ((int(bucket) + 1) / 10.0)
            count += hist[bucket]
            respdata.append(
                (
                    f'meshping_pings_bucket{{name="{target.name}",'
                    f'target="{target.addr}",le="{nextping:.2f}"}} {count}'
                )
            )
        respdata.append(
            (
                f'meshping_pings_bucket{{name="{target.name}",'
                f'target="{target.addr}",le="+Inf"}} {count}'
            )
        )

    return HttpResponse("\n".join(respdata) + "\n", content_type="text/plain")


# route /network.svg
#
# note: plantuml in the ubuntu 24.04 apt repo is version 1.2020.02, which gives a
#       broken output. newer version required, known to work with 1.2024.4
#
# TODO split out some logic here, this probably reduces the amount of local vars
# pylint: disable=too-many-locals
@require_http_methods(["GET"])
def network(request):
    targets = Target.objects.all()
    uniq_hops = {}
    uniq_links = set()

    for target in targets:
        prev_hop = "SELF"
        prev_dist = 0
        for hop in target_traceroute(target):
            hop_id = hop["address"].replace(":", "_").replace(".", "_")

            # Check if we know this hop already. If we do, just skip ahead.
            if hop_id not in uniq_hops:
                # Fill in the blanks for missing hops, if any
                while hop["distance"] > prev_dist + 1:
                    dummy_id = str(randint(10000000, 99999999))
                    dummy = {
                        "id": dummy_id,
                        "distance": (prev_dist + 1),
                        "address": None,
                        "name": None,
                        "target": None,
                        "whois": None,
                    }
                    uniq_hops[dummy_id] = dummy
                    uniq_links.add((prev_hop, dummy_id))
                    prev_hop = dummy_id
                    prev_dist += 1

                # Now render the hop itself
                hop_id = hop["address"].replace(":", "_").replace(".", "_")
                uniq_hops.setdefault(hop_id, dict(hop, id=hop_id, target=None))
                uniq_links.add((prev_hop, hop_id))

                # make sure we show the most recent state info
                if (
                    uniq_hops[hop_id]["state"] != hop["state"]
                    and uniq_hops[hop_id]["time"] < hop["time"]
                ):
                    uniq_hops[hop_id].update(state=hop["state"], time=hop["time"])

            if hop["address"] == target.addr:
                uniq_hops[hop_id]["target"] = target

            prev_hop = hop_id
            prev_dist = hop["distance"]

    now = datetime.now()

    context = {
        "hostname": socket.gethostname(),
        "now": now.strftime("%Y-%m-%d %H:%M:%S"),
        "targets": targets,
        "uniq_hops": uniq_hops,
        "uniq_links": sorted(uniq_links),
        "uniq_hops_sorted": [uniq_hops[hop] for hop in sorted(uniq_hops.keys())],
    }
    tpl = loader.get_template("network.puml.j2").render(context)

    plantuml = run_command(
        ["plantuml", "-tsvg", "-p"],
        input=tpl.encode("utf-8"),
        capture_output=True,
        check=False,
    )

    if plantuml.stderr:
        return HttpResponseServerError(
            plantuml.stderr.decode("utf-8") + "\n\n===\n\n" + tpl,
            content_type="text/plain",
        )

    resp = HttpResponse(plantuml.stdout, content_type="image/svg+xml")

    resp["refresh"] = "43200"  # 12h
    resp["Cache-Control"] = "max-age=36000, public"  # 10h

    resp["content-disposition"] = (
        'inline; filename="meshping_'
        f'{now.strftime("%Y-%m-%d_%H-%M-%S")}_network.svg"'
    )

    return resp


# route /peer
#
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
@require_http_methods(["POST"])
def peer(request):
    request_json = json.loads(request.body)

    if request_json is None:
        return HttpResponseBadRequest("Please send content-type:application/json")

    if not isinstance(request_json.get("targets"), list):
        return HttpResponseBadRequest("need targets as a list")

    ret_stats = []
    if4 = Ifaces4()

    for target in request_json["targets"]:
        if not isinstance(target, dict):
            return HttpResponseBadRequest("targets must be dicts")
        if (
            not target.get("name", "").strip()
            or not target.get("addr", "").strip()
            or not isinstance(target.get("local"), bool)
        ):
            return HttpResponseBadRequest("required field missing in target")

        target["name"] = target["name"].strip()
        target["addr"] = target["addr"].strip()

        if if4.is_interface(target["addr"]):
            # no need to ping my own interfaces, ignore
            continue

        if target["local"] and not if4.is_local(target["addr"]):
            continue

        # See if we know this target already, otherwise create it.
        tgt, created = Target.objects.get_or_create(
            addr=target["addr"], name=target["name"]
        )
        if created:
            tgt_meta, _created = Meta.objects.get_or_create(target=tgt)
            tgt_meta.is_foreign = True
            tgt_meta.save()
        target_stats, _created = Statistics.objects.get_or_create(target=tgt)
        ret_stats.append(model_to_dict(target_stats))

    return JsonResponse(
        {
            "success": True,
            "targets": ret_stats,
        }
    )


# route /api/resolve/<str:name>
@require_http_methods(["GET"])
def resolve(request, name):
    try:
        return JsonResponse(
            {
                "success": True,
                "addrs": [
                    info[4][0]
                    for info in socket.getaddrinfo(name, 0, 0, socket.SOCK_STREAM)
                ],
            }
        )
    except socket.gaierror as err:
        return JsonResponse({"success": False, "error": str(err)})


# route /api/stats
#
# TODO possible race condition: upon deletion, the /api/targets endpoint might have
#      incorrect assumptions due to the statistics objects disappearing
@require_http_methods(["DELETE"])
def stats(request):
    Statistics.objects.all().delete()
    Meta.objects.all().update(state=TargetState.UNKNOWN)
    return JsonResponse({"success": True})


# route /api/targets
#
# django ensures a valid http request method, so we do not need a return value
# pylint: disable=inconsistent-return-statements
#
# TODO do not crash when the uniqueness constraint is not met for new targets
# TODO nasty race condition, retrieving objects can fail when target was just deleted
@require_http_methods(["GET", "POST"])
def targets_endpoint(request):
    if request.method == "GET":
        targets = []

        for target in Target.objects.all():
            target_stats = Statistics.objects.filter(target=target).values()
            if not target_stats:
                target_stats = {"sent": 0, "lost": 0, "recv": 0, "sum": 0}
            else:
                target_stats = target_stats[0]
            succ = 0
            loss = 0
            if target_stats["sent"] > 0:
                succ = target_stats["recv"] / target_stats["sent"] * 100
                loss = (
                    (target_stats["sent"] - target_stats["recv"])
                    / target_stats["sent"]
                    * 100
                )

            # the browser cannot deserialize JSON with Infinity, but this value is
            # very comfortable for comparisons, we want to keep it
            if target_stats["min"] == float("inf"):
                target_stats["min"] = 0

            target_meta, _created = Meta.objects.get_or_create(target=target)

            targets.append(
                dict(
                    target_stats,
                    addr=target.addr,
                    name=target.name,
                    state=target_meta.state,
                    error=target_meta.error,
                    succ=succ,
                    loss=loss,
                    traceroute=target_meta.traceroute,
                    route_loop=target_meta.route_loop,
                )
            )

        return JsonResponse({"targets": targets})

    if request.method == "POST":
        request_json = json.loads(request.body)
        if "target" not in request_json:
            return HttpResponseBadRequest("missing target")
        target = request_json["target"]
        added = []
        if "@" not in target:
            try:
                addrinfo = socket.getaddrinfo(target, 0, 0, socket.SOCK_STREAM)
            except socket.gaierror as err:
                return JsonResponse(
                    {
                        "success": False,
                        "target": target,
                        "error": str(err),
                    }
                )
            for info in addrinfo:
                addr = info[4][0]
                Target(name=target, addr=addr).save()
                added.append(f"{target}@{addr}")
        else:
            tname, addr = target.split("@")
            Target(name=tname, addr=addr).save()
            added.append(target)
        return JsonResponse(
            {
                "success": True,
                "targets": added,
            }
        )


# route /api/targets/<str:target>
@require_http_methods(["DELETE"])
def edit_target(request, target):
    if request.method == "DELETE":
        Target.objects.filter(addr=target).delete()
        return JsonResponse({"success": True})
