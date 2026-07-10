from django.urls import path
from . import views

app_name = 'creditos_ventas'

urlpatterns = [
    path('ventas/pendientes/', views.CuotaVentaListView.as_view(), name='cuota_venta_list'),
    path('ventas/factura/<int:factura_id>/', views.plan_cuotas_venta, name='plan_cuotas_venta'),
    path('ventas/factura/<int:factura_id>/pagar/', views.pagar_cuotas_venta, name='pagar_cuotas_venta'),
    path('ventas/pago/<int:pago_id>/pdf/', views.pago_cuota_venta_pdf, name='pago_cuota_venta_pdf'),

    path('compras/pendientes/', views.CuotaCompraListView.as_view(), name='cuota_compra_list'),
    path('compras/compra/<int:compra_id>/', views.plan_cuotas_compra, name='plan_cuotas_compra'),
    path('compras/compra/<int:compra_id>/pagar/', views.pagar_cuotas_compra, name='pagar_cuotas_compra'),
    path('compras/pago/<int:pago_id>/pdf/', views.pago_cuota_compra_pdf, name='pago_cuota_compra_pdf'),
]
