from django.urls import path

from . import views

app_name = "detection"

urlpatterns = [
    path("diagnosis/", views.leaf_diagnosis_view, name="leaf_diagnosis"),
    path("upload/", views.upload_scan, name="upload_scan"),
    path("result/<int:scan_id>/", views.scan_result, name="scan_result"),
]
