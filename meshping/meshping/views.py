import json
import os
import socket

from django.http import HttpResponse, HttpResponseBadRequest, JsonResponse
from django.views.decorators.http import require_http_methods
from django.template import loader
from markupsafe import Markup

from .models import Statistics, Target


# route /
# TODO do not load icons from disk for every request
# TODO find a better method for finding the icons to not have an absolute path here
# TODO make local development possible when node modules are on disk (relative path)
def index(request):
    template = loader.get_template('index.html.j2')
    # icons_dir = "/opt/meshping/ui/node_modules/bootstrap-icons/icons/"
    icons_dir = "../ui/node_modules/bootstrap-icons/icons/"
    icons_dir = os.path.join(os.path.dirname(__file__), icons_dir)
    icons = {
        filename: Markup(open(os.path.join(icons_dir, filename), "r").read())
        for filename in os.listdir(icons_dir)
    }
    context = {
        "Hostname": socket.gethostname(),
        "icons": icons,
    }
    return HttpResponse(template.render(context, request))


# route /api/targets
# TODO add state to response for each target
# TODO add error to response for each target
# TODO add traceroute to response for each target
# TODO add route_loop to response for each target
# TODO do not crash when the uniqueness constraint is not met for new targets
@require_http_methods(["GET", "POST"])
def targets(request):
    if request.method == "GET":
            targets = []

            for target in Target.objects.all():
                target_stats = Statistics.objects.filter(target=target).values()
                if not target_stats:
                    target_stats = {
                        "sent": 0, "lost": 0, "recv": 0, "sum":  0
                    }
                else:
                    target_stats = target_stats[0]
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
#                        state=target.state,
#                        error=target.error,
                        succ=succ,
                        loss=loss,
#                        traceroute=target.traceroute,
#                        route_loop=target.route_loop,
                    )
                )

            return JsonResponse({'targets': targets})

    elif request.method == "POST":
        request_json = json.loads(request.body)
        if "target" not in request_json:
            return HttpResponseBadRequest("missing target")
        target = request_json["target"]
        added = []
        if "@" not in target:
            try:
                addrinfo = socket.getaddrinfo(target, 0, 0, socket.SOCK_STREAM)
            except socket.gaierror as err:
                return JsonResponse({
                    'success': False,
                    'target': target,
                    'error': str(err),
                })
            for info in addrinfo:
                addr = info[4][0]
                Target(name=target, addr=addr).save()
                added.append(f"{target}@{addr}")
        else:
            tname, addr = target.split('@')
            Target(name=tname, addr=addr).save()
            added.append(target)
        return JsonResponse({
            'success': True,
            'targets': added,
        })
