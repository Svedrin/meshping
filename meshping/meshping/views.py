import os
import socket

from django.http import HttpResponse, JsonResponse
from django.views.decorators.http import require_http_methods
from django.template import loader
from markupsafe import Markup

from .models import Statistics, Target


# route /
# TODO do not load icons from disk for every request
# TODO find a better method for finding the icons to not have an absolute path here
def index(request):
    template = loader.get_template('index.html.j2')
    # icons_dir = "/opt/meshping/ui/node_modules/bootstrap-icons/icons/"
    icons_dir = "../ui/node_modules/bootstrap-icons/icons/"
    icons_dir = os.path.join(os.path.dirname(__file__), icons_dir)
    print(icons_dir)
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
@require_http_methods(["GET", "POST"])
def targets(request):
    if request.method == "GET":
            targets = []

            for target in Target.objects.all():
                target_stats = Statistics.objects.filter(target=target).values()[0]
                if not target_stats:
                    target_stats = {
                        "sent": 0, "lost": 0, "recv": 0, "sum":  0
                    }
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
        pass

#@app.route("/api/targets", methods=["GET", "POST"])
#    async def targets():
#        if request.method == "GET":
#            targets = []
#
#            for target in mp.all_targets():
#                target_stats = target.statistics
#                succ = 0
#                loss = 0
#                if target_stats["sent"] > 0:
#                    succ = target_stats["recv"] / target_stats["sent"] * 100
#                    loss = (target_stats["sent"] - target_stats["recv"]) / target_stats["sent"] * 100
#                targets.append(
#                    dict(
#                        target_stats,
#                        addr=target.addr,
#                        name=target.name,
#                        state=target.state,
#                        error=target.error,
#                        succ=succ,
#                        loss=loss,
#                        traceroute=target.traceroute,
#                        route_loop=target.route_loop,
#                    )
#                )
#
#            return jsonify(success=True, targets=targets)
#
#        if request.method == "POST":
#            request_json = await request.get_json()
#            if "target" not in request_json:
#                return "missing target", 400
#
#            target = request_json["target"]
#            added = []
#
#            if "@" not in target:
#                try:
#                    addrinfo = socket.getaddrinfo(target, 0, 0, socket.SOCK_STREAM)
#                except socket.gaierror as err:
#                    return jsonify(success=False, target=target, error=str(err))
#
#                for info in addrinfo:
#                    target_with_addr = "%s@%s" % (target, info[4][0])
#                    mp.add_target(target_with_addr)
#                    added.append(target_with_addr)
#            else:
#                mp.add_target(target)
#                added.append(target)
#
#            return jsonify(success=True, targets=added)
#
#        abort(400)
