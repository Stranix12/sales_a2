from decimal import Decimal
from django.db.models import F, Avg, Sum
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from billing.models import Product
from .models import Purchase, PurchaseDetail
from .forms import PurchaseForm, PurchaseDetailFormSet, PurchaseFilterForm
from .exports import export_purchase_excel, export_purchase_pdf


@login_required
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
            purchase.tax = subtotal * Decimal('0.15')
            purchase.total = purchase.subtotal + purchase.tax
            purchase.save()

            # Reto 1: la compra reabastece inventario (la venta resta, la compra suma)
            for detail in saved_details:
                Product.objects.filter(pk=detail.product_id).update(
                    stock=F('stock') + detail.quantity
                )

            messages.success(request, f'Purchase #{purchase.id} created!')
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
def purchase_detail(request, pk):
    purchase = get_object_or_404(
        Purchase.objects.select_related('supplier').prefetch_related('details__product'),
        pk=pk,
    )
    return render(request, 'purchasing/purchase_detail.html', {'purchase': purchase})


@login_required
def purchase_export_pdf(request, pk):
    """Exporta una compra individual a PDF (cabecera + líneas)."""
    purchase = get_object_or_404(
        Purchase.objects.select_related('supplier').prefetch_related('details__product'),
        pk=pk,
    )
    return export_purchase_pdf(purchase)


@login_required
def purchase_export_excel(request, pk):
    """Exporta una compra individual a Excel (cabecera + líneas)."""
    purchase = get_object_or_404(
        Purchase.objects.select_related('supplier').prefetch_related('details__product'),
        pk=pk,
    )
    return export_purchase_excel(purchase)


@login_required
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
def purchase_delete(request, pk):
    purchase = get_object_or_404(Purchase, pk=pk)
    if request.method == 'POST':
        pid = purchase.id
        purchase.delete()
        messages.success(request, f'Purchase #{pid} deleted!')
        return redirect('purchasing:purchase_list')
    return render(request, 'purchasing/purchase_confirm_delete.html', {'object': purchase})
