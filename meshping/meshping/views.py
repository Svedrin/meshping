import json
import os
import socket
from datetime import datetime

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

from .meshping import histodraw
from .models import Statistics, Target, Meta, target_histograms


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
#
# TODO is the metrics output valid prometheus format when no values are present?
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
def network(request):
    return HttpResponseServerError("not implemented")


# route /peer
def peer(request):
    return HttpResponseServerError("not implemented")


# route /api/resolve/<str:name>
def resolve(request, **kwargs):
    return HttpResponseServerError("not implemented")


# route /api/stats
def stats(request):
    return HttpResponseServerError("not implemented")


# route /api/targets
#
# django ensures a valid http request method, so we do not need a return value
# pylint: disable=inconsistent-return-statements
#
# TODO add state to response for each target
# TODO add error to response for each target
# TODO add traceroute to response for each target
# TODO add route_loop to response for each target
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
