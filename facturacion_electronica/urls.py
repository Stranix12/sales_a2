from django.urls import path
from . import views

app_name = 'facturacion_electronica'

urlpatterns = [
    path('factura/<int:invoice_id>/enviar-sri/', views.enviar_al_sri, name='enviar_al_sri'),
    path('factura/<int:invoice_id>/xml/', views.descargar_xml, name='descargar_xml'),
    path('factura/<int:invoice_id>/ride/', views.descargar_ride, name='descargar_ride'),
]
