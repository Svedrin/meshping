import os
import socket

from django.http import HttpResponse
from django.template import loader
from markupsafe import Markup
from .models import Target


# TODO do not load icons from disk for every request
# TODO find a better method for finding the icons to not have an absolute path here
def index(request):
    template = loader.get_template('index.html.j2')
    # icons_dir = "/opt/meshping/ui/node_modules/bootstrap-icons/icons/"
    icons_dir = "../ui/node_modules/bootstrap-icons/icons/"
    icons_dir = os.path.join(os.path.dirname(__file__), icons_dir)
    print(icons_dir)
    icons = dict(
        icons={
            filename: Markup(open(os.path.join(icons_dir, filename), "r").read())
            for filename in os.listdir(icons_dir)
        }
    )
    context = {
        "Hostname": socket.gethostname(),
        "icons": icons,
    }
    return HttpResponse(template.render(context, request))
