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
]
