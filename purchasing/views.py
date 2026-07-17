from decimal import Decimal, ROUND_HALF_UP
from django.db.models import F, Avg, Sum, ProtectedError
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from billing.models import Product
from creditos_compras.services import generar_cuotas_compra
from shared.decorators import any_permission_required
from .models import Purchase, PurchaseDetail
from .forms import PurchaseForm, PurchaseDetailFormSet, PurchaseFilterForm
from .exports import export_purchase_excel, export_purchase_pdf


@login_required
@any_permission_required(('purchasing.view_purchase', 'purchasing.add_purchase',
                          'purchasing.change_purchase', 'purchasing.delete_purchase'))
def purchase_list(request):
    """Reto 3: filtra por proveedor y por rango de fechas / año."""
    purchases = Purchase.objects.select_related('supplier')

    filter_form = PurchaseFilterForm(request.GET)
    filter_form.is_valid()
    cd = filter_form.cleaned_data

    if cd.get('supplier'):
        purchases = purchases.filter(supplier=cd['supplier'])
    if cd.get('date_from') and cd.get('date_to'):
        # __range → BETWEEN fecha_desde AND fecha_hasta
        purchases = purchases.filter(purchase_date__date__range=(cd['date_from'], cd['date_to']))
    elif cd.get('date_from'):
        purchases = purchases.filter(purchase_date__date__gte=cd['date_from'])
    elif cd.get('date_to'):
        purchases = purchases.filter(purchase_date__date__lte=cd['date_to'])
    if cd.get('year'):
        # __year → extrae el año de purchase_date
        purchases = purchases.filter(purchase_date__year=cd['year'])

    return render(request, 'purchasing/purchase_list.html', {
        'purchases': purchases,
        'filter_form': filter_form,
    })


@login_required
@permission_required('purchasing.add_purchase', raise_exception=True)
def purchase_create(request):
    if request.method == 'POST':
        form = PurchaseForm(request.POST)
        formset = PurchaseDetailFormSet(request.POST)
        if form.is_valid() and formset.is_valid():
            purchase = form.save()
            formset.instance = purchase
            saved_details = formset.save()
            subtotal = sum(d.subtotal for d in purchase.details.all())
            purchase.subtotal = subtotal
            purchase.tax = (subtotal * Decimal('0.15')).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
            purchase.total = purchase.subtotal + purchase.tax
            purchase.save()

            # Crédito de compras: CONTADO queda cancelada al instante (sin
            # cuotas); CREDITO genera el plan de cuotas mensuales.
            if form.cleaned_data['tipo_pago'] == 'CREDITO':
                generar_cuotas_compra(purchase, form.cleaned_data['num_cuotas'])
            else:
                purchase.tipo_pago = 'CONTADO'
                purchase.saldo = Decimal('0')
                purchase.estado = 'PAGADA'
                purchase.save(update_fields=['tipo_pago', 'saldo', 'estado'])

            # Reto 1: la compra reabastece inventario (la venta resta, la compra suma)
            for detail in saved_details:
                Product.objects.filter(pk=detail.product_id).update(
                    stock=F('stock') + detail.quantity
                )

            messages.success(request, f'Compra #{purchase.id} creada correctamente.')
            return redirect('purchasing:purchase_list')
    else:
        form = PurchaseForm()
        formset = PurchaseDetailFormSet()
    return render(request, 'purchasing/purchase_form.html', {
        'form': form,
        'formset': formset,
        'title': 'Nueva Compra',
    })


@login_required
@permission_required('purchasing.view_purchase', raise_exception=True)
def purchase_detail(request, pk):
    purchase = get_object_or_404(
        Purchase.objects.select_related('supplier').prefetch_related('details__product'),
        pk=pk,
    )
    return render(request, 'purchasing/purchase_detail.html', {'purchase': purchase})


@login_required
@permission_required('purchasing.view_purchase', raise_exception=True)
def purchase_export_pdf(request, pk):
    """Exporta una compra individual a PDF (cabecera + líneas)."""
    purchase = get_object_or_404(
        Purchase.objects.select_related('supplier').prefetch_related('details__product'),
        pk=pk,
    )
    return export_purchase_pdf(purchase)


@login_required
@permission_required('purchasing.view_purchase', raise_exception=True)
def purchase_export_excel(request, pk):
    """Exporta una compra individual a Excel (cabecera + líneas)."""
    purchase = get_object_or_404(
        Purchase.objects.select_related('supplier').prefetch_related('details__product'),
        pk=pk,
    )
    return export_purchase_excel(purchase)


@login_required
@permission_required('purchasing.view_purchase_report', raise_exception=True)
def purchase_report(request):
    """Reto 4: costo promedio de compra por producto."""
    report = (
        PurchaseDetail.objects
        .values('product__name')
        .annotate(avg_cost=Avg('unit_cost'), total_qty=Sum('quantity'))
        .order_by('product__name')
    )
    return render(request, 'purchasing/purchase_report.html', {'report': report})


@login_required
@permission_required('purchasing.delete_purchase', raise_exception=True)
def purchase_delete(request, pk):
    purchase = get_object_or_404(Purchase, pk=pk)
    if request.method == 'POST':
        pid = purchase.id
        try:
            purchase.delete()
        except ProtectedError:
            # La compra tiene un plan de cuotas (crédito de compras): no se
            # puede borrar sin antes eliminar/cancelar sus cuotas.
            messages.error(
                request,
                f'No se puede eliminar la compra #{pid}: tiene un plan de cuotas '
                'asociado (compra a crédito). Elimina primero sus cuotas o pagos.'
            )
            return redirect('purchasing:purchase_detail', pk=pid)
        messages.success(request, f'Compra #{pid} eliminada correctamente.')
        return redirect('purchasing:purchase_list')
    return render(request, 'purchasing/purchase_confirm_delete.html', {'object': purchase})
