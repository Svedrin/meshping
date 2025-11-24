from django.urls import path
from . import views


# TODO decide about and deal with caching on /ui resources (django staticfiles)
urlpatterns = [
    path("", views.index, name="index"),
    path("histogram/<str:node>/<str:target>.png", views.histogram, name="histogram"),
    path("metrics", views.metrics, name="metrics"),
    path("network.svg", views.network, name="network"),
    path("peer", views.peer, name="peer"),
    path("api/resolve/<str:name>", views.resolve, name="resolve"),
    path("api/stats", views.stats, name="stats"),
    path("api/targets", views.targets_endpoint, name="targets"),
    path("api/targets/<str:target>", views.edit_target, name="target"),
]
