from django.urls import path

from . import views

app_name = "adminpanel"

urlpatterns = [
    path("", views.admin_login_view, name="login"),
    path("logout/", views.admin_logout_view, name="logout"),
    path("dashboard/", views.dashboard_view, name="dashboard"),
    path("users/", views.users_view, name="users"),
    path("messages/", views.messages_view, name="messages"),
    path("diagnoses/", views.diagnoses_view, name="diagnoses"),
    path("users/<int:user_id>/toggle-active/", views.toggle_user_active_view, name="toggle_user_active"),
    path("users/<int:user_id>/toggle-staff/", views.toggle_user_staff_view, name="toggle_user_staff"),
    path("messages/<int:message_id>/toggle-resolved/", views.toggle_message_resolved_view, name="toggle_message_resolved"),

    # Resource Management
    path("crops/", views.crops_view, name="crops"),
    path("crops/add/", views.crop_upsert_view, name="crop_add"),
    path("crops/<int:crop_id>/edit/", views.crop_upsert_view, name="crop_edit"),
    path("crops/<int:crop_id>/delete/", views.crop_delete_view, name="crop_delete"),

    path("diseases/", views.diseases_view, name="diseases"),
    path("diseases/add/", views.disease_upsert_view, name="disease_add"),
    path("diseases/<int:disease_id>/edit/", views.disease_upsert_view, name="disease_edit"),
    path("diseases/<int:disease_id>/delete/", views.disease_delete_view, name="disease_delete"),

    path("datasets/", views.datasets_view, name="datasets"),
    path("datasets/<int:dataset_id>/delete/", views.dataset_delete_view, name="dataset_delete"),
]
