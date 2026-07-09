from django.contrib import admin
from django.urls import path, include, re_path
from django.conf import settings
from django.views.static import serve

urlpatterns = [
    path('admin/', admin.site.urls),
    path('accounts/', include('django.contrib.auth.urls')),
    path('', include('billing.urls')),
    path('purchases/', include('purchasing.urls')),
    path('security/', include('security.urls')),
]

# Sirve los archivos subidos (MEDIA) también con DEBUG=False: el helper
# static() solo funciona en desarrollo, así que en Render las imágenes de
# productos daban 404. Whitenoise solo cubre STATIC, no MEDIA; para este
# proyecto (sin S3) servirlas con la vista serve de Django es suficiente.
urlpatterns += [
    re_path(r'^media/(?P<path>.*)$', serve, {'document_root': settings.MEDIA_ROOT}),
]
