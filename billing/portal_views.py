"""Portal del Cliente (/portal/...): autoservicio para usuarios con rol
"Cliente" vinculados a un registro de Customer.

A diferencia de las vistas internas (que usan permisos de Django, globales
por modelo), aquí el control de acceso es **por fila**: cada vista opera
únicamente sobre los datos del cliente vinculado al usuario logueado
(request.user.customer_account). Por eso el rol Cliente no recibe ningún
permiso de modelo en setup_roles.
"""
from decimal import Decimal, ROUND_HALF_UP
from functools import wraps

from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render

from . import paypal
from .electronic import asignar_datos_electronicos
from .invoice_export import invoice_pdf_response
from .models import Customer, Invoice, InvoiceDetail, Product
from .views import _apply_payment
from shared.emails import send_invoice_email


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
def portal_invoice_xml(request, pk):
    """El cliente descarga el XML autorizado de SU factura (comprobante SRI)."""
    from facturacion_electronica.views import xml_response
    invoice = _own_invoice_or_404(request, pk)
    return xml_response(invoice)


@customer_required
def portal_invoice_ride(request, pk):
    """El cliente descarga el RIDE (PDF del comprobante) de SU factura."""
    from facturacion_electronica.ride import ride_pdf_response
    invoice = _own_invoice_or_404(request, pk)
    return ride_pdf_response(invoice)


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


# =====================================================================
# Tienda: catálogo + carrito (en sesión) + checkout
# =====================================================================
# El carrito vive en la sesión como {product_id(str): cantidad(int)} — sin
# modelos nuevos. Solo guarda ids y cantidades: el precio SIEMPRE se lee del
# producto al momento (nunca se confía en datos viejos de la sesión).

def _get_cart(request):
    return request.session.get('cart') or {}


def _save_cart(request, cart):
    request.session['cart'] = cart
    request.session.modified = True


def _cart_lines(request):
    """Líneas del carrito con datos frescos de BD. Los productos que ya no
    existen o fueron desactivados se eliminan del carrito (con aviso)."""
    cart = _get_cart(request)
    products = {p.pk: p for p in
                Product.objects.filter(pk__in=[int(k) for k in cart], is_active=True)
                .select_related('brand')}
    lines, stale = [], []
    for key, qty in cart.items():
        product = products.get(int(key))
        if product is None:
            stale.append(key)
            continue
        qty = int(qty)
        lines.append({'product': product, 'qty': qty,
                      'subtotal': product.unit_price * qty})
    if stale:
        for key in stale:
            cart.pop(key, None)
        _save_cart(request, cart)
        messages.warning(request, 'Algunos productos de tu carrito ya no están disponibles y fueron retirados.')
    subtotal = sum((l['subtotal'] for l in lines), Decimal('0'))
    return lines, subtotal


@customer_required
def portal_catalog(request):
    """Catálogo: productos activos, con búsqueda por nombre/marca/categoría."""
    q = request.GET.get('q', '').strip()
    products = (Product.objects.filter(is_active=True)
                .select_related('brand', 'group').order_by('name'))
    if q:
        products = products.filter(
            Q(name__icontains=q) | Q(brand__name__icontains=q) | Q(group__name__icontains=q))
    return render(request, 'billing/portal/catalog.html', {
        'products': products,
        'q': q,
    })


@customer_required
def portal_cart_add(request, pk):
    if request.method != 'POST':
        return redirect('billing:portal_catalog')
    product = get_object_or_404(Product, pk=pk, is_active=True)
    try:
        qty = max(1, int(request.POST.get('qty', 1)))
    except (TypeError, ValueError):
        qty = 1

    cart = _get_cart(request)
    current = int(cart.get(str(pk), 0))
    wanted = current + qty
    if product.stock <= 0:
        messages.error(request, f'"{product.name}" está agotado.')
        return redirect('billing:portal_catalog')
    if wanted > product.stock:
        wanted = product.stock
        messages.warning(request, f'Solo hay {product.stock} unidad(es) de "{product.name}": '
                                  'tu carrito quedó con el máximo disponible.')
    else:
        messages.success(request, f'"{product.name}" agregado al carrito.')
    cart[str(pk)] = wanted
    _save_cart(request, cart)
    # 'next' permite volver a donde estaba el usuario, pero solo rutas
    # internas (que empiecen con '/'): nunca un redirect a otro dominio.
    next_url = request.POST.get('next', '')
    if next_url.startswith('/'):
        return redirect(next_url)
    return redirect('billing:portal_catalog')


@customer_required
def portal_cart(request):
    lines, subtotal = _cart_lines(request)
    tax = (subtotal * Decimal('0.15')).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    return render(request, 'billing/portal/cart.html', {
        'lines': lines,
        'subtotal': subtotal,
        'tax': tax,
        'total': subtotal + tax,
    })


@customer_required
def portal_cart_update(request, pk):
    if request.method != 'POST':
        return redirect('billing:portal_cart')
    cart = _get_cart(request)
    key = str(pk)
    if key not in cart:
        return redirect('billing:portal_cart')
    try:
        qty = int(request.POST.get('qty', 1))
    except (TypeError, ValueError):
        qty = 1
    if qty < 1:
        cart.pop(key, None)
    else:
        product = get_object_or_404(Product, pk=pk)
        if qty > product.stock:
            qty = product.stock or 1
            messages.warning(request, f'Solo hay {product.stock} unidad(es) de "{product.name}".')
        cart[key] = qty
    _save_cart(request, cart)
    return redirect('billing:portal_cart')


@customer_required
def portal_cart_remove(request, pk):
    if request.method != 'POST':
        return redirect('billing:portal_cart')
    cart = _get_cart(request)
    cart.pop(str(pk), None)
    _save_cart(request, cart)
    return redirect('billing:portal_cart')


@customer_required
def portal_checkout(request):
    """Convierte el carrito en una factura del cliente logueado.

    Mismo patrón blindado que invoice_create: transacción + select_for_update
    sobre los productos, validación de stock contra los datos bloqueados, y
    todo-o-nada (si una línea falla, no se compra nada). La factura nace
    PENDIENTE: el cliente aterriza en su detalle, donde está el botón de
    Pagar con PayPal."""
    if request.method != 'POST':
        return redirect('billing:portal_cart')
    cart = _get_cart(request)
    if not cart:
        messages.error(request, 'Tu carrito está vacío.')
        return redirect('billing:portal_catalog')

    invoice = None
    with transaction.atomic():
        locked = {p.pk: p for p in
                  Product.objects.select_for_update().filter(pk__in=[int(k) for k in cart])}
        errors, lines = [], []
        for key, qty in cart.items():
            product = locked.get(int(key))
            qty = int(qty)
            if product is None or not product.is_active:
                errors.append('Un producto de tu carrito ya no está disponible.')
            elif qty > product.stock:
                errors.append(f'Stock insuficiente para "{product.name}": '
                              f'disponible {product.stock}, en tu carrito {qty}.')
            elif qty >= 1:
                lines.append((product, qty))

        if errors or not lines:
            for err in errors or ['Tu carrito está vacío.']:
                messages.error(request, err)
        else:
            invoice = Invoice.objects.create(customer=request.customer)
            subtotal = Decimal('0')
            for product, qty in lines:
                detail = InvoiceDetail.objects.create(
                    invoice=invoice, product=product, quantity=qty,
                    unit_price=product.unit_price)
                subtotal += detail.subtotal
                product.stock -= qty
                product.save(update_fields=['stock'])
            invoice.subtotal = subtotal
            invoice.tax = (subtotal * Decimal('0.15')).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
            invoice.total = invoice.subtotal + invoice.tax
            invoice.save()
            asignar_datos_electronicos(invoice)

    if invoice is None:
        return redirect('billing:portal_cart')

    send_invoice_email(invoice)  # fuera de la transacción (no retiene el lock)
    _save_cart(request, {})
    messages.success(request, f'¡Pedido realizado! Se generó tu factura {invoice.numero_factura}. '
                              'Puedes pagarla ahora mismo con PayPal.')
    return redirect('billing:portal_invoice_detail', pk=invoice.pk)
