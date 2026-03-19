from pathlib import Path

from django import forms
from django.conf import settings
from PIL import Image, UnidentifiedImageError

from .models import Diagnosis, LeafDiagnosis


def _validate_image_file(uploaded_file, *, field_name):
    allowed_extensions = set(
        getattr(settings, "LEAF_DIAGNOSIS_ALLOWED_EXTENSIONS", ["jpg", "jpeg", "png"])
    )
    max_size = getattr(settings, "LEAF_DIAGNOSIS_MAX_UPLOAD_SIZE", 5 * 1024 * 1024)

    extension = Path(uploaded_file.name).suffix.lower().lstrip(".")
    if extension not in allowed_extensions:
        raise forms.ValidationError(
            f"Unsupported file type for {field_name}. Please upload a JPG, JPEG, or PNG image."
        )

    if uploaded_file.size > max_size:
        raise forms.ValidationError(
            f"{field_name} must be smaller than {max_size // (1024 * 1024)} MB."
        )

    try:
        uploaded_file.seek(0)
        image = Image.open(uploaded_file)
        image.verify()
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise forms.ValidationError("Please upload a valid image file.") from exc
    finally:
        uploaded_file.seek(0)


class DiagnosisForm(forms.ModelForm):
    class Meta:
        model = Diagnosis
        fields = ("leaf_image",)
        widgets = {
            "leaf_image": forms.ClearableFileInput(
                attrs={
                    "class": "form-control form-input",
                    "accept": ".jpg,.jpeg,.png,image/jpeg,image/png",
                }
            ),
        }

    def clean_leaf_image(self):
        uploaded_file = self.cleaned_data["leaf_image"]
        _validate_image_file(uploaded_file, field_name="Leaf image")
        return uploaded_file


class LeafDiagnosisForm(forms.ModelForm):
    class Meta:
        model = LeafDiagnosis
        fields = ("image",)
        widgets = {
            "image": forms.ClearableFileInput(
                attrs={
                    "class": "form-control form-input",
                    "accept": ".jpg,.jpeg,.png,image/jpeg,image/png",
                }
            ),
        }

    def clean_image(self):
        uploaded_file = self.cleaned_data["image"]
        _validate_image_file(uploaded_file, field_name="Leaf image")
        return uploaded_file
