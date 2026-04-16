from django.db import models
from django.conf import settings

class FarmLocation(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="farm_location"
    )
    latitude = models.FloatField()
    longitude = models.FloatField()
    city_name = models.CharField(max_length=100, blank=True)

    def __str__(self):
        return f"{self.user.username}'s Farm - {self.city_name or 'Unknown Location'}"

class AgriculturalDataset(models.Model):
    name = models.CharField(max_length=200)
    description = models.TextField()
    dataset_file = models.FileField(upload_to="datasets/")
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-uploaded_at"]

    def __str__(self):
        return self.name
