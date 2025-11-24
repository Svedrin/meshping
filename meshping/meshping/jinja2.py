from jinja2 import Environment
from django.urls import reverse
from django.templatetags.static import static


def environment(**options):
    env = Environment(variable_start_string="{[", variable_end_string="]}", **options)
    env.globals.update(
        {
            "static": static,
            "url": reverse,
        }
    )
    return env
