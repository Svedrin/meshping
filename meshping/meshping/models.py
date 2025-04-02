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


# TODO decide on max_length, even though ignored by sqlite
# TODO uniqueness constraint `UNIQUE (target_id, field)`
class Statistics(models.Model):
    target = models.ForeignKey(Target, on_delete=models.CASCADE)
    field = models.CharField(max_length=255)
    value = models.FloatField()


# TODO check if the CharField maps to SQLite TEXT + decide on max_length
# TODO uniqueness constraint `UNIQUE (target_id, field)`
class Meta(models.Model):
    target = models.ForeignKey(Target, on_delete=models.CASCADE)
    field = models.CharField(max_length=255)
    value = models.CharField(max_length=255)
