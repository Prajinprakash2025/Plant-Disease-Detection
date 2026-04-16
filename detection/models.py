from django.conf import settings
from django.db import models


class Crop(models.Model):
    name = models.CharField(max_length=120, unique=True)
    name_ml = models.CharField(max_length=150, blank=True, verbose_name="Name (Malayalam)")
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class Disease(models.Model):
    name = models.CharField(max_length=150)
    name_ml = models.CharField(max_length=150, blank=True, verbose_name="Name (Malayalam)")
    crop = models.ForeignKey(Crop, on_delete=models.CASCADE, related_name="diseases")
    symptoms = models.TextField()
    symptoms_ml = models.TextField(blank=True, verbose_name="Symptoms (Malayalam)")
    treatment_recommendations = models.TextField()
    treatment_recommendations_ml = models.TextField(blank=True, verbose_name="Treatment (Malayalam)")
    preventive_measures = models.TextField()
    preventive_measures_ml = models.TextField(blank=True, verbose_name="Prevention (Malayalam)")

    class Meta:
        ordering = ["crop__name", "name"]
        unique_together = ("name", "crop")

    def __str__(self):
        return f"{self.name} ({self.crop.name})"


class Diagnosis(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="diagnoses",
    )
    leaf_image = models.ImageField(upload_to="leaf_scans/")
    predicted_disease = models.ForeignKey(
        Disease,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="diagnoses",
    )
    confidence_score = models.FloatField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Scan #{self.pk} - {self.user}"


class LeafDiagnosis(models.Model):
    SOURCE_LOCAL_MODEL = "local_model"
    SOURCE_GEMINI_API = "gemini_api"
    SOURCE_CHOICES = (
        (SOURCE_LOCAL_MODEL, "Local Model"),
        (SOURCE_GEMINI_API, "Gemini API"),
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="leaf_diagnosis_logs",
    )
    image = models.ImageField(upload_to="uploads/")
    original_filename = models.CharField(max_length=255, blank=True)
    plant_name = models.CharField(max_length=255, blank=True)
    predicted_disease = models.CharField(max_length=255, blank=True)
    confidence = models.FloatField(null=True, blank=True)
    source = models.CharField(
        max_length=20,
        choices=SOURCE_CHOICES,
        default=SOURCE_LOCAL_MODEL,
    )
    treatment_guidance = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Diagnosis #{self.pk} - {self.user}"
