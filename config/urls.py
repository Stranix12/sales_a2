from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('admin/', admin.site.urls),
    path('accounts/', include('django.contrib.auth.urls')),
    path('', include('billing.urls')),
    path('purchases/', include('purchasing.urls')),
    path('security/', include('security.urls')),  
]

# Sirve los archivos subidos (MEDIA) durante el desarrollo (DEBUG=True).
urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
