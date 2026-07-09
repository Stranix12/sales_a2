"""Portal del Cliente (/portal/...): autoservicio para usuarios con rol
"Cliente" vinculados a un registro de Customer.

A diferencia de las vistas internas (que usan permisos de Django, globales
por modelo), aquí el control de acceso es **por fila**: cada vista opera
únicamente sobre los datos del cliente vinculado al usuario logueado
(request.user.customer_account). Por eso el rol Cliente no recibe ningún
permiso de modelo en setup_roles.
"""
from functools import wraps

from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from . import paypal
from .invoice_export import invoice_pdf_response
from .models import Customer, Invoice
from .views import _apply_payment


def customer_required(view_func):
    """El usuario debe estar logueado Y vinculado a un Customer.

    Un usuario interno (Vendedor/Admin) que entre a /portal/ por error no
    tiene cuenta de cliente: se le explica y se le regresa al home."""
    @wraps(view_func)
    @login_required
    def wrapper(request, *args, **kwargs):
        customer = getattr(request.user, 'customer_account', None)
        if customer is None:
            messages.error(request, 'Tu usuario no está vinculado a ningún cliente. '
                                    'Pide al administrador que vincule tu cuenta.')
            return redirect('billing:home')
        request.customer = customer
        return view_func(request, *args, **kwargs)
    return wrapper


def _own_invoice_or_404(request, pk):
    """La factura pedida, solo si pertenece al cliente del usuario. Para
    cualquier otra responde 404 (ni siquiera confirma que exista)."""
    return get_object_or_404(
        Invoice.objects.select_related('customer').prefetch_related('details__product', 'payment_logs__user'),
        pk=pk, customer=request.customer,
    )


@customer_required
def portal_invoice_list(request):
    """Mis facturas: solo las del cliente vinculado."""
    invoices = Invoice.objects.filter(customer=request.customer).order_by('-invoice_date')
    pendientes = invoices.filter(payment_status='PENDIENTE').count()
    return render(request, 'billing/portal/invoice_list.html', {
        'invoices': invoices,
        'pendientes': pendientes,
        'customer': request.customer,
    })


@customer_required
def portal_invoice_detail(request, pk):
    invoice = _own_invoice_or_404(request, pk)
    return render(request, 'billing/portal/invoice_detail.html', {
        'invoice': invoice,
        'paypal_configured': paypal.is_configured(),
    })


@customer_required
def portal_invoice_pdf(request, pk):
    invoice = _own_invoice_or_404(request, pk)
    return invoice_pdf_response(invoice)


@customer_required
def portal_paypal_start(request, pk):
    """El cliente paga SU factura con PayPal (mismo flujo que el interno,
    pero con chequeo de propiedad en vez de permiso de modelo)."""
    invoice = _own_invoice_or_404(request, pk)
    if request.method != 'POST':
        return redirect('billing:portal_invoice_detail', pk=pk)
    if invoice.payment_status == 'PAGADA':
        messages.info(request, f'La factura {invoice.numero_factura} ya estaba pagada.')
        return redirect('billing:portal_invoice_detail', pk=pk)
    if not paypal.is_configured():
        messages.error(request, 'El pago en línea no está disponible por el momento.')
        return redirect('billing:portal_invoice_detail', pk=pk)

    try:
        order_id, approve_url = paypal.create_order(
            invoice, request,
            return_urlname='billing:portal_paypal_return',
            cancel_urlname='billing:portal_paypal_cancel')
    except paypal.PayPalError as exc:
        messages.error(request, str(exc))
        return redirect('billing:portal_invoice_detail', pk=pk)

    request.session[f'paypal_order_{invoice.pk}'] = order_id
    return redirect(approve_url)


@customer_required
def portal_paypal_return(request, pk):
    invoice = _own_invoice_or_404(request, pk)
    order_id = request.GET.get('token') or request.session.get(f'paypal_order_{invoice.pk}')
    if invoice.payment_status == 'PAGADA':
        messages.info(request, f'La factura {invoice.numero_factura} ya estaba pagada.')
        return redirect('billing:portal_invoice_detail', pk=pk)
    if not order_id:
        messages.error(request, 'No se recibió la orden de PayPal.')
        return redirect('billing:portal_invoice_detail', pk=pk)

    try:
        status, capture_id = paypal.capture_order(order_id)
    except paypal.PayPalError as exc:
        messages.error(request, str(exc))
        return redirect('billing:portal_invoice_detail', pk=pk)

    if status != 'COMPLETED':
        messages.error(request, f'PayPal no completó el pago (estado: {status}).')
        return redirect('billing:portal_invoice_detail', pk=pk)

    _apply_payment(invoice, request.user, 'paypal',
                   note=f'PayPal order {order_id} / capture {capture_id} (portal cliente)')
    request.session.pop(f'paypal_order_{invoice.pk}', None)
    messages.success(request, f'¡Pago recibido! Tu factura {invoice.numero_factura} quedó pagada.')
    return redirect('billing:portal_invoice_detail', pk=pk)


@customer_required
def portal_paypal_cancel(request, pk):
    invoice = _own_invoice_or_404(request, pk)
    request.session.pop(f'paypal_order_{invoice.pk}', None)
    messages.info(request, 'Pago cancelado. Tu factura sigue pendiente.')
    return redirect('billing:portal_invoice_detail', pk=pk)


class PortalProfileForm(forms.ModelForm):
    """El cliente edita SOLO sus datos de contacto. Nombre y DNI/RUC quedan
    fuera a propósito: son la identidad fiscal del comprobante y los maneja
    el personal del negocio."""
    class Meta:
        model = Customer
        fields = ['email', 'phone', 'address']
        widgets = {
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
            'phone': forms.TextInput(attrs={'class': 'form-control'}),
            'address': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }
        labels = {'email': 'Email', 'phone': 'Teléfono', 'address': 'Dirección'}


@customer_required
def portal_profile(request):
    """Mis datos: ver identidad (solo lectura) y editar contacto."""
    if request.method == 'POST':
        form = PortalProfileForm(request.POST, instance=request.customer)
        if form.is_valid():
            form.save()
            messages.success(request, 'Tus datos de contacto fueron actualizados.')
            return redirect('billing:portal_profile')
    else:
        form = PortalProfileForm(instance=request.customer)
    return render(request, 'billing/portal/profile.html', {
        'form': form,
        'customer': request.customer,
    })
