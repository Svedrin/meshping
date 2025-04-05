from django.db import models


# TODO decide on max_length, even though ignored by sqlite
class Target(models.Model):
    addr = models.CharField(max_length=255, unique=True)
    name = models.CharField(max_length=255)

    class Meta:
        unique_together = ("addr", "name")


# TODO uniqueness constraint `UNIQUE (target_id, timestamp, bucket)`
class Histogram(models.Model):
    target = models.ForeignKey(Target, on_delete=models.CASCADE)
    timestamp = models.IntegerField()
    bucket = models.IntegerField()
    count = models.IntegerField(default=1)


class Statistics(models.Model):
    target = models.OneToOneField(Target, on_delete=models.CASCADE, primary_key=True)
    sent = models.FloatField(default=0.0)
    lost = models.FloatField(default=0.0)
    recv = models.FloatField(default=0.0)
    sum = models.FloatField(default=0.0)
    last = models.FloatField(default=0.0)
    max = models.FloatField(default=0.0)
    min = models.FloatField(default=float("inf"))
    avg15m = models.FloatField(default=0.0)
    avg6h = models.FloatField(default=0.0)
    avg24h = models.FloatField(default=0.0)


# pylint: disable=too-many-ancestors
class TargetState(models.TextChoices):
    UP = "up"
    DOWN = "down"
    UNKNOWN = "unknown"
    ERROR = "error"


# TODO decide on max_length, even though ignored by sqlite
# TODO uniqueness constraint `UNIQUE (target_id, field)`
class Meta(models.Model):
    target = models.OneToOneField(Target, on_delete=models.CASCADE, primary_key=True)
    state = models.CharField(
        max_length=10, choices=TargetState.choices, default=TargetState.DOWN
    )
    route_loop = models.BooleanField(default=False)
    traceroute = models.JSONField(max_length=2048, default=list)
    # lkgt = last known good traceroute
    lkgt = models.JSONField(max_length=2048, default=list)
    error = models.CharField(max_length=255, null=True, default=None)
    is_foreign = models.BooleanField(default=False)
