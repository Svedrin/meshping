from django.db import models


# TODO decide on max_length, even though ignored by sqlite
class Target(models.Model):
    addr = models.CharField(max_length=255, unique=True)
    name = models.CharField(max_length=255)

    class Meta:
        unique_together = ('addr', 'name')


# TODO uniqueness constraint `UNIQUE (target_id, timestamp, bucket)`
class Histogram(models.Model):
    target = models.ForeignKey(Target, on_delete=models.CASCADE)
    timestamp = models.IntegerField()
    bucket = models.IntegerField()
    count = models.IntegerField(default=1)


class Statistics(models.Model):
    target = models.OneToOneField(Target, on_delete=models.CASCADE, primary_key=True)
    sent =  models.FloatField(default=0.0)
    lost =  models.FloatField(default=0.0)
    recv =  models.FloatField(default=0.0)
    sum =  models.FloatField(default=0.0)
    last =  models.FloatField(default=0.0)
    max =  models.FloatField(default=0.0)
    min =  models.FloatField(default=0.0)
    avg15m =  models.FloatField(default=0.0)
    avg6h =  models.FloatField(default=0.0)
    avg24h =  models.FloatField(default=0.0)


# TODO check if the CharField maps to SQLite TEXT + decide on max_length
# TODO uniqueness constraint `UNIQUE (target_id, field)`
class Meta(models.Model):
    target = models.ForeignKey(Target, on_delete=models.CASCADE)
    field = models.CharField(max_length=255)
    value = models.CharField(max_length=255)
