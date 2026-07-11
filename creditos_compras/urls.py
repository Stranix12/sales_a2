from django.urls import path
from . import views

app_name = 'creditos_compras'

# Se incluye bajo el prefijo creditos/compras/ (ver config/urls.py), así las
# rutas quedan idénticas a las que tenía creditos_ventas antes del traslado.
urlpatterns = [
    path('pendientes/', views.CuotaCompraListView.as_view(), name='cuota_compra_list'),
    path('compra/<int:compra_id>/', views.plan_cuotas_compra, name='plan_cuotas_compra'),
    path('compra/<int:compra_id>/pagar/', views.pagar_cuotas_compra, name='pagar_cuotas_compra'),
    path('pago/<int:pago_id>/pdf/', views.pago_cuota_compra_pdf, name='pago_cuota_compra_pdf'),
]
