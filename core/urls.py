from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('admin/', admin.site.urls),
    path('django-admin/', admin.site.urls),  # kept for existing usage
    path('adminpanel/', include('adminpanel.urls')),  # custom admin panel UI
    path('', include('account.urls')), 
    path('', include('detection.urls')),
    path('dashboard/', include('dashboard.urls')),
]

# This line allows Django to serve user-uploaded media files (like leaf images) during development
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
