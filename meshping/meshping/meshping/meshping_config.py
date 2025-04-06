# TODO add implementation for values from environment
# TODO decide about option for config file, and automatic combination with docker
#      environment variables
#
# pylint: disable=too-many-instance-attributes
class MeshpingConfig:
    def __init__(self):
        self.ping_timeout = 5
        self.ping_interval = 30

        self.traceroute_interval = 900
        self.traceroute_timeout = 0.5
        self.traceroute_packets = 1
        self.traceroute_ratelimit_interval = 2

        self.peers = ""
        self.peering_interval = 30
        self.peering_timeout = 30

        # TODO make config options in this object consistent, use seconds
        self.whois_cache_validiy_h = 72

        # TODO make config options in this object consistent, use seconds
        self.histogram_period = 3
