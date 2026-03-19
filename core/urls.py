from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('django-admin/', admin.site.urls),
    path('', include('account.urls')), 
    path('', include('detection.urls')),
    path('dashboard/', include('dashboard.urls')),
]

# This line allows Django to serve user-uploaded media files (like leaf images) during development
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
