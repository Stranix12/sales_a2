from django.urls import path
from . import views

app_name = 'creditos_ventas'

urlpatterns = [
    path('ventas/pendientes/', views.CuotaVentaListView.as_view(), name='cuota_venta_list'),
    path('ventas/factura/<int:factura_id>/', views.plan_cuotas_venta, name='plan_cuotas_venta'),
    path('ventas/factura/<int:factura_id>/pagar/', views.pagar_cuotas_venta, name='pagar_cuotas_venta'),
    path('ventas/pago/<int:pago_id>/pdf/', views.pago_cuota_venta_pdf, name='pago_cuota_venta_pdf'),
]
