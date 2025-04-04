from django.apps import AppConfig


class MeshpingConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "meshping"

    def ready(self):
        # TODO start background threads for ping, traceroute, peers
        pass
