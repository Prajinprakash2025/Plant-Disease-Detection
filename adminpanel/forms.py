from django import forms
from django.contrib.auth.forms import AuthenticationForm

from account.forms import StyledFieldsMixin
from detection.models import Crop, Disease


class AdminLoginForm(StyledFieldsMixin, AuthenticationForm):
    placeholders = {
        "username": "Admin username",
        "password": "Admin password",
    }
    autocomplete_map = {
        "username": "username",
        "password": "current-password",
    }

    error_messages = {
        **AuthenticationForm.error_messages,
        "not_staff": "This account does not have admin access.",
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.style_fields()

    def clean(self):
        cleaned_data = super().clean()
        if self.user_cache and not self.user_cache.is_staff:
            raise forms.ValidationError(
                self.error_messages["not_staff"],
                code="not_staff",
            )
        return cleaned_data


class CropForm(StyledFieldsMixin, forms.ModelForm):
    class Meta:
        model = Crop
        fields = ["name", "description"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.style_fields()


class DiseaseForm(StyledFieldsMixin, forms.ModelForm):
    class Meta:
        model = Disease
        fields = ["name", "crop", "symptoms", "treatment_recommendations", "preventive_measures"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.style_fields()
