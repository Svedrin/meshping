from itertools import zip_longest
from django.db import models
import pandas


# TODO decide on max_length, even though ignored by sqlite
class Target(models.Model):
    addr = models.CharField(max_length=255, unique=True)
    name = models.CharField(max_length=255)

    class Meta:
        unique_together = ("addr", "name")

    @property
    def label(self):
        if self.name == self.addr:
            return self.name
        return f"{self.name} ({self.addr})"


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
        max_length=10, choices=TargetState.choices, default=TargetState.UNKNOWN
    )
    route_loop = models.BooleanField(default=False)
    traceroute = models.JSONField(max_length=2048, default=list)
    # lkgt = last known good traceroute
    lkgt = models.JSONField(max_length=2048, default=list)
    error = models.CharField(max_length=255, null=True, default=None)
    is_foreign = models.BooleanField(default=False)


# TODO consider making this a Target property, but take care that Histogram is defined
#      before Target
#
# pivot method: flip the dataframe: turn each value of the "bucket" DB column into a
# separate column in the DF, using the timestamp as the index and the count for the
# values. None-existing positions in the DF are filled with zero.
def target_histograms(target):
    df = pandas.DataFrame.from_dict(
        Histogram.objects.filter(target=target).order_by("timestamp", "bucket").values()
    )
    df["timestamp"] = pandas.to_datetime(df["timestamp"], unit="s")
    return df.pivot(
        index="timestamp",
        columns="bucket",
        values="count",
    ).fillna(0)


# TODO consider making this a Target property, but take care that Meta is defined
#      before Target
def target_traceroute(target):
    target_meta, _created = Meta.objects.get_or_create(target=target)

    curr = target_meta.traceroute
    lkgt = target_meta.lkgt  # last known good traceroute
    if not curr or not lkgt or len(lkgt) < len(curr):
        # we probably don't know all the nodes, but the ones we do know are up
        return [dict(hop, state="up") for hop in curr]
    if curr[-1]["address"] == target.addr:
        # Trace has reached the target itself, thus all hops are up
        return [dict(hop, state="up") for hop in curr]

    # Check with lkgt to see which hops are still there
    result = []
    for lkgt_hop, curr_hop in zip_longest(lkgt, curr):
        if lkgt_hop is None:
            # This should not be able to happen, because we checked
            # len(lkgt) < len(curr) above.
            raise ValueError("last known good traceroute: hop is None")
        if curr_hop is None:
            # hops missing from current traceroute are down
            result.append(dict(lkgt_hop, state="down"))
        elif curr_hop.get("address") != lkgt_hop.get("address"):
            result.append(dict(curr_hop, state="different"))
        else:
            result.append(dict(curr_hop, state="up"))
    return result
