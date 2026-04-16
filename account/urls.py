from django.urls import path
from . import views

app_name = 'account'

urlpatterns = [
    path('', views.home, name='home'),
    path('about/', views.about_view, name='about'),
    path('contact/', views.contact_view, name='contact'),
    path('admin-login/', views.admin_login_view, name='admin_login'),
    path('admin-login/logout/', views.admin_logout_view, name='admin_logout'),
    path('admin-login/dashboard/', views.admin_dashboard_view, name='admin_dashboard'),
    path('admin-login/users/', views.admin_users_view, name='admin_users'),
    path('admin-login/messages/', views.admin_messages_view, name='admin_messages'),
    path('admin-login/users/<int:user_id>/toggle-active/', views.toggle_user_active_view, name='toggle_user_active'),
    path('admin-login/users/<int:user_id>/toggle-staff/', views.toggle_user_staff_view, name='toggle_user_staff'),
    path('admin-login/messages/<int:message_id>/toggle-resolved/', views.toggle_message_resolved_view, name='toggle_message_resolved'),
    path('signup/', views.signup_view, name='signup'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('profile/', views.profile_view, name='profile'),
    path('membership/', views.membership_view, name='membership'),
    path('membership/checkout/', views.checkout_view, name='checkout'),
    path('membership/confirm-payment/', views.confirm_payment_view, name='confirm_payment'),
    path('admin-login/membership-requests/', views.admin_membership_requests_view, name='admin_membership_requests'),
    path('admin-login/membership-requests/<int:membership_id>/handle/', views.handle_membership_request_view, name='handle_membership_request'),
]
