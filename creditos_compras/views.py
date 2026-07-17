"""Pantallas del crédito de compras: consulta de cuotas pendientes, plan de
cuotas de una compra, registro de pagos y comprobante PDF de cada pago.

Reutiliza los helpers parametrizados de creditos_ventas.views
(_render_plan/_procesar_pago) y sus plantillas compartidas: es el mismo
flujo aplicado a Purchase + CuotaCompra en lugar de Invoice + CuotaVenta.
"""
from django.contrib.auth.decorators import login_required, permission_required
from django.shortcuts import get_object_or_404
from django.views.generic import ListView

from billing.mixins import ExportListMixin
from creditos_ventas.views import _procesar_pago, _render_plan
from purchasing.models import Purchase
from shared.mixins import AnyPermissionRequiredMixin
from .forms import CuotaFilterForm
from .models import CuotaCompra, PagoCuotaCompra
from .receipts import pago_cuota_compra_pdf_response
from .services import registrar_pagos_compra


# ============================================================= listado =====
class CuotaCompraListView(ExportListMixin, AnyPermissionRequiredMixin, ListView):
    """Consulta de cuotas de compra (por defecto, solo las pendientes)."""
    model = CuotaCompra
    permission_required = ('creditos_compras.view_cuotacompra', 'creditos_compras.add_cuotacompra',
                           'creditos_compras.change_cuotacompra', 'creditos_compras.delete_cuotacompra')
    template_name = 'creditos_compras/cuota_compra_list.html'
    context_object_name = 'items'
    paginate_by = 15
    export_title = 'Cuotas de Compra'
    columns_session_key = 'cuota_compra_columns'
    export_columns = [
        {'key': 'compra',             'label': 'Compra',       'field': 'compra.document_number',  'default': True},
        {'key': 'proveedor',          'label': 'Proveedor',    'field': 'compra.supplier',          'default': True},
        {'key': 'numero',             'label': '# Cuota',      'field': 'numero',                   'default': True},
        {'key': 'fecha_vencimiento',  'label': 'Vencimiento',  'field': 'fecha_vencimiento',        'default': True},
        {'key': 'valor',              'label': 'Valor',        'field': 'valor',                    'default': True},
        {'key': 'saldo',              'label': 'Saldo',        'field': 'saldo',                    'default': True},
        {'key': 'estado',             'label': 'Estado',       'field': 'estado',                   'default': True},
    ]

    def get_queryset(self):
        qs = super().get_queryset().select_related('compra', 'compra__supplier')
        data = self.request.GET.copy()
        data.setdefault('estado', 'PENDIENTE')
        self.filter_form = CuotaFilterForm(data)
        self.filter_form.is_valid()
        estado = self.filter_form.cleaned_data.get('estado')
        if estado:
            qs = qs.filter(estado=estado)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['filter_form'] = self.filter_form
        return ctx


# ======================================================= plan de cuotas =====
@login_required
@permission_required('creditos_compras.view_cuotacompra', raise_exception=True)
def plan_cuotas_compra(request, compra_id):
    purchase = get_object_or_404(Purchase.objects.select_related('supplier'), pk=compra_id)
    cuotas = purchase.cuotas.all()
    pagos = PagoCuotaCompra.objects.filter(cuota__compra=purchase).select_related('cuota')
    return _render_plan(
        request, purchase, tipo='compra', cuotas=cuotas, pagos=pagos,
        volver_url='purchasing:purchase_detail',
        pagar_url='creditos_compras:pagar_cuotas_compra',
        pdf_url='creditos_compras:pago_cuota_compra_pdf',
    )


# ============================================================= pagos =====
@login_required
@permission_required('creditos_compras.add_pagocuotacompra', raise_exception=True)
def pagar_cuotas_compra(request, compra_id):
    purchase = get_object_or_404(Purchase, pk=compra_id)
    pendientes = list(purchase.cuotas.filter(estado='PENDIENTE'))
    return _procesar_pago(
        request, purchase, tipo='compra', pendientes=pendientes, registrar_fn=registrar_pagos_compra,
        plan_url_name='creditos_compras:plan_cuotas_compra', plan_kwarg='compra_id',
    )


# ================================================ comprobantes de pago =====
@login_required
@permission_required('creditos_compras.view_pagocuotacompra', raise_exception=True)
def pago_cuota_compra_pdf(request, pago_id):
    pago = get_object_or_404(
        PagoCuotaCompra.objects.select_related('cuota__compra__supplier'), pk=pago_id)
    return pago_cuota_compra_pdf_response(pago)
