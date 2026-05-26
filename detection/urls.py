from django.urls import path

from . import views

app_name = "detection"

urlpatterns = [
    path("diagnosis/", views.leaf_diagnosis_view, name="leaf_diagnosis"),
    path("upload/", views.upload_scan, name="upload_scan"),
    path("result/<int:scan_id>/", views.scan_result, name="scan_result"),
    path("diagnosis/result/<int:diagnosis_id>/", views.leaf_diagnosis_result_view, name="leaf_diagnosis_result"),
    path("gemini-verify/", views.gemini_verify, name="gemini_verify"),
    path("translate-diagnosis/", views.translate_diagnosis_content, name="translate_diagnosis"),
    path("tts-proxy/", views.tts_proxy, name="tts_proxy"),
]
