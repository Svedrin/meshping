# TODO add implementation for values from environment
# TODO decide about option for config file, and automatic combination with docker
#      environment variables
class MeshpingConfig:
    def __init__(self):
        self.ping_timeout = 1
        self.ping_interval = 1
        self.histogram_period = 1
