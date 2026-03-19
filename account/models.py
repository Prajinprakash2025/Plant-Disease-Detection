from django.conf import settings
from django.db import models


class ContactMessage(models.Model):
    name = models.CharField(max_length=150)
    email = models.EmailField()
    subject = models.CharField(max_length=200)
    message = models.TextField()
    is_resolved = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.subject} - {self.name}"


class MembershipProfile(models.Model):
    PLAN_FREE = "free"
    PLAN_PREMIUM = "premium"
    PLAN_CHOICES = (
        (PLAN_FREE, "Free"),
        (PLAN_PREMIUM, "Premium Demo"),
    )

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="membership_profile",
    )
    plan = models.CharField(max_length=20, choices=PLAN_CHOICES, default=PLAN_FREE)
    upgraded_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["user__username"]

    @property
    def is_premium(self):
        return self.plan == self.PLAN_PREMIUM

    def __str__(self):
        return f"{self.user.username} - {self.get_plan_display()}"
