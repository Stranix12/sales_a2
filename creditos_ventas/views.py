from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.contrib.auth.mixins import PermissionRequiredMixin
from django.core.exceptions import ValidationError
from django.shortcuts import render, redirect, get_object_or_404
from django.views.generic import ListView

from billing.mixins import ExportListMixin
from billing.models import Invoice
from purchasing.models import Purchase
from .forms import RegistrarPagoForm, CuotaPagoFormSet, CuotaFilterForm
from .models import CuotaVenta, PagoCuotaVenta, CuotaCompra, PagoCuotaCompra
from .receipts import pago_cuota_venta_pdf_response, pago_cuota_compra_pdf_response
from .services import (
    registrar_pagos_venta, registrar_pagos_compra,
)


# ============================================================= listados =====
class CuotaVentaListView(ExportListMixin, PermissionRequiredMixin, ListView):
    """Consulta de cuotas de venta (por defecto, solo las pendientes)."""
    model = CuotaVenta
    permission_required = 'creditos_ventas.view_cuotaventa'
    template_name = 'creditos_ventas/cuota_venta_list.html'
    context_object_name = 'items'
    paginate_by = 15
    export_title = 'Cuotas de Venta'
    columns_session_key = 'cuota_venta_columns'
    export_columns = [
        {'key': 'factura',            'label': 'Factura',      'field': 'factura.numero_factura', 'default': True},
        {'key': 'cliente',            'label': 'Cliente',      'field': 'factura.customer',        'default': True},
        {'key': 'numero',             'label': '# Cuota',      'field': 'numero',                  'default': True},
        {'key': 'fecha_vencimiento',  'label': 'Vencimiento',  'field': 'fecha_vencimiento',        'default': True},
        {'key': 'valor',              'label': 'Valor',        'field': 'valor',                    'default': True},
        {'key': 'saldo',              'label': 'Saldo',        'field': 'saldo',                    'default': True},
        {'key': 'estado',             'label': 'Estado',       'field': 'estado',                   'default': True},
    ]

    def get_queryset(self):
        qs = super().get_queryset().select_related('factura', 'factura__customer')
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


class CuotaCompraListView(ExportListMixin, PermissionRequiredMixin, ListView):
    """Consulta de cuotas de compra (por defecto, solo las pendientes)."""
    model = CuotaCompra
    permission_required = 'creditos_ventas.view_cuotacompra'
    template_name = 'creditos_ventas/cuota_compra_list.html'
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
def _contraparte_info(documento, tipo):
    """(contraparte, etiqueta, título) — venta muestra el cliente, compra el proveedor."""
    if tipo == 'venta':
        return documento.customer, 'Cliente', f'Factura {documento.numero_factura or documento.pk}'
    return documento.supplier, 'Proveedor', f'Compra #{documento.pk} ({documento.document_number})'


def _render_plan(request, documento, *, tipo, cuotas, pagos, template='creditos_ventas/plan_cuotas.html'):
    contraparte, contraparte_label, titulo = _contraparte_info(documento, tipo)
    if tipo == 'venta':
        volver_url, pagar_url = 'billing:invoice_detail', 'creditos_ventas:pagar_cuotas_venta'
    else:
        volver_url, pagar_url = 'purchasing:purchase_detail', 'creditos_ventas:pagar_cuotas_compra'

    return render(request, template, {
        'documento': documento, 'tipo': tipo, 'cuotas': cuotas, 'pagos': pagos,
        'contraparte': contraparte, 'contraparte_label': contraparte_label,
        'titulo': titulo, 'volver_url': volver_url, 'pagar_url': pagar_url,
    })


@login_required
@permission_required('creditos_ventas.view_cuotaventa', raise_exception=True)
def plan_cuotas_venta(request, factura_id):
    invoice = get_object_or_404(Invoice.objects.select_related('customer'), pk=factura_id)
    cuotas = invoice.cuotas.all()
    pagos = PagoCuotaVenta.objects.filter(cuota__factura=invoice).select_related('cuota')
    return _render_plan(request, invoice, tipo='venta', cuotas=cuotas, pagos=pagos)


@login_required
@permission_required('creditos_ventas.view_cuotacompra', raise_exception=True)
def plan_cuotas_compra(request, compra_id):
    purchase = get_object_or_404(Purchase.objects.select_related('supplier'), pk=compra_id)
    cuotas = purchase.cuotas.all()
    pagos = PagoCuotaCompra.objects.filter(cuota__compra=purchase).select_related('cuota')
    return _render_plan(request, purchase, tipo='compra', cuotas=cuotas, pagos=pagos)


# ============================================================= pagos =====
def _procesar_pago(request, documento, *, tipo, pendientes, registrar_fn, plan_url_name, plan_kwarg):
    if request.method == 'POST':
        pago_form = RegistrarPagoForm(request.POST)
        formset = CuotaPagoFormSet(request.POST)
        if pago_form.is_valid() and formset.is_valid():
            cuotas_por_id = {c.pk: c for c in pendientes}
            seleccionadas = [
                (cuotas_por_id[row['cuota_id']], row['monto'])
                for row in formset.cleaned_data
                if row and row.get('pagar') and row.get('cuota_id') in cuotas_por_id
            ]
            try:
                registrar_fn(
                    seleccionadas, pago_form.cleaned_data['fecha'],
                    observacion=pago_form.cleaned_data.get('observacion', ''),
                    user=request.user,
                )
            except ValidationError as exc:
                for msg in (exc.messages if hasattr(exc, 'messages') else [str(exc)]):
                    messages.error(request, msg)
            else:
                messages.success(request, 'Pago(s) registrado(s) correctamente.')
                return redirect(plan_url_name, **{plan_kwarg: documento.pk})
    else:
        pago_form = RegistrarPagoForm()
        formset = CuotaPagoFormSet(initial=[{'cuota_id': c.pk} for c in pendientes])

    filas = list(zip(pendientes, formset.forms))
    contraparte, contraparte_label, titulo = _contraparte_info(documento, tipo)

    return render(request, 'creditos_ventas/pagar_cuotas.html', {
        'documento': documento, 'tipo': tipo, 'pago_form': pago_form, 'formset': formset,
        'filas': filas, 'contraparte': contraparte, 'contraparte_label': contraparte_label,
        'titulo': titulo, 'plan_url': plan_url_name, 'plan_kwarg': plan_kwarg,
    })


@login_required
@permission_required('creditos_ventas.add_pagocuotaventa', raise_exception=True)
def pagar_cuotas_venta(request, factura_id):
    invoice = get_object_or_404(Invoice, pk=factura_id)
    pendientes = list(invoice.cuotas.filter(estado='PENDIENTE'))
    return _procesar_pago(
        request, invoice, tipo='venta', pendientes=pendientes, registrar_fn=registrar_pagos_venta,
        plan_url_name='creditos_ventas:plan_cuotas_venta', plan_kwarg='factura_id',
    )


@login_required
@permission_required('creditos_ventas.add_pagocuotacompra', raise_exception=True)
def pagar_cuotas_compra(request, compra_id):
    purchase = get_object_or_404(Purchase, pk=compra_id)
    pendientes = list(purchase.cuotas.filter(estado='PENDIENTE'))
    return _procesar_pago(
        request, purchase, tipo='compra', pendientes=pendientes, registrar_fn=registrar_pagos_compra,
        plan_url_name='creditos_ventas:plan_cuotas_compra', plan_kwarg='compra_id',
    )


# ================================================ comprobantes de pago =====
@login_required
@permission_required('creditos_ventas.view_pagocuotaventa', raise_exception=True)
def pago_cuota_venta_pdf(request, pago_id):
    pago = get_object_or_404(
        PagoCuotaVenta.objects.select_related('cuota__factura__customer'), pk=pago_id)
    return pago_cuota_venta_pdf_response(pago)


@login_required
@permission_required('creditos_ventas.view_pagocuotacompra', raise_exception=True)
def pago_cuota_compra_pdf(request, pago_id):
    pago = get_object_or_404(
        PagoCuotaCompra.objects.select_related('cuota__compra__supplier'), pk=pago_id)
    return pago_cuota_compra_pdf_response(pago)
