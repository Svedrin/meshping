from django.apps import AppConfig
from .meshping.meshping_config import MeshpingConfig as MPCOnfig


class MeshpingConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "meshping"

    # TODO decide for long-term layout: standard threads, async, scheduling library
    # TODO start background threads for traceroute, peers
    # TODO with the current thread model, django complains about db access before app
    #      initialization is completed
    # TODO create background task for db housekeeping (prune_histograms)
    def ready(self):
        # delayed import, otherwise we will get AppRegistryNotReady
        # pylint: disable=import-outside-toplevel
        from .meshping.ping_thread import PingThread
        from .meshping.traceroute_thread import TracerouteThread

        mp_config = MPCOnfig()
        ping_thread = PingThread(mp_config=mp_config, daemon=True)
        traceroute_thread = TracerouteThread(mp_config=mp_config)

        ping_thread.start()
        traceroute_thread.start()
