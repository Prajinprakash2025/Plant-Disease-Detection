from django.urls import path
from . import views

app_name = 'dashboard'

urlpatterns = [
    path('', views.dashboard_home, name='home'),
    path('section/<str:section_key>/', views.dashboard_section, name='section'),
    path('update-location/', views.update_location, name='update_location'),
    path('upload-dataset/', views.upload_dataset, name='upload_dataset'),
]
