import json
import math
from decimal import Decimal
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.contrib.auth.mixins import PermissionRequiredMixin
from django.views.generic import ListView, CreateView, UpdateView, DeleteView, DetailView
from django.urls import reverse_lazy
from django.utils import timezone
from django.db import transaction
from django.db.models import Sum, F, DecimalField, ExpressionWrapper
from django.db.models.functions import TruncMonth
from .models import *
from .forms import (BrandForm, BrandFilterForm, ProductFilterForm, ProductForm,
                    CustomerForm, CustomerFilterForm, InvoiceForm, InvoiceDetailFormSet,
                    ProductGroupForm, ProductGroupFilterForm, SupplierForm, SupplierFilterForm,
                    InvoiceFilterForm)
from .mixins import ExportListMixin
from .electronic import asignar_datos_electronicos
from .invoice_export import invoice_pdf_response
from . import paypal
from creditos_ventas.services import generar_cuotas_venta
from facturacion_electronica.services import generar_comprobante
from shared.decorators import audit_action
from shared.emails import send_invoice_email


_MESES_ABREV = ['Ene', 'Feb', 'Mar', 'Abr', 'May', 'Jun',
                'Jul', 'Ago', 'Sep', 'Oct', 'Nov', 'Dic']


def _ultimos_meses(n=6):
    """Lista de (año, mes) de los últimos n meses, del más viejo al actual."""
    hoy = timezone.localtime() if timezone.is_aware(timezone.now()) else timezone.now()
    y, m = hoy.year, hoy.month
    meses = []
    for _ in range(n):
        meses.append((y, m))
        m -= 1
        if m == 0:
            m, y = 12, y - 1
    meses.reverse()
    return meses


def _area_chart(values, labels):
    """Calcula la geometría SVG (polilínea + área rellena) de la serie de
    ventas por mes, escalada a un viewBox fijo. Todo el cálculo vive aquí
    para que la plantilla solo pinte strings ya listos."""
    W, H = 640, 200
    top, bottom, left, right = 14, 168, 14, 626
    max_val = max(values) or 1
    n = len(values)
    def x_at(i):
        return left + (i * (right - left) / (n - 1) if n > 1 else 0)
    def y_at(v):
        return bottom - (v / max_val) * (bottom - top)
    pts = [(round(x_at(i), 1), round(y_at(v), 1)) for i, v in enumerate(values)]
    polyline = ' '.join(f'{x},{y}' for x, y in pts)
    area = ('M ' + f'{pts[0][0]},{bottom} '
            + ' '.join(f'L {x},{y}' for x, y in pts)
            + f' L {pts[-1][0]},{bottom} Z')
    return {
        'w': W, 'h': H, 'baseline': bottom, 'polyline': polyline, 'area': area,
        'points': [{'x': x, 'y': y, 'label': labels[i], 'value': values[i]}
                   for i, (x, y) in enumerate(pts)],
    }


# === HOME (Página principal / Dashboard) ===
@login_required
def home(request):
    """Dashboard: KPIs + gráficas (SVG propio) calculadas desde los modelos
    existentes (Invoice, InvoiceDetail, Product, Customer). Sin dependencias
    externas ni endpoints extra — todo se resuelve en esta vista."""
    # Un usuario del portal (rol Cliente, sin roles internos) no debe ver el
    # dashboard del negocio (ingresos, inventario…): su "home" es su portal.
    u = request.user
    if (u.is_authenticated and getattr(u, 'customer_account', None)
            and not u.is_superuser and not u.groups.exclude(name='Cliente').exists()):
        return redirect('billing:portal_catalog')

    money = ExpressionWrapper(F('unit_price') * F('stock'), output_field=DecimalField())

    # --- KPIs ---
    revenue = Invoice.objects.aggregate(s=Sum('total'))['s'] or Decimal('0')
    inventory_value = Product.objects.aggregate(v=Sum(money))['v'] or Decimal('0')

    # --- Ventas por mes (últimos 6 meses, con relleno en 0) ---
    meses = _ultimos_meses(6)
    ventas = (Invoice.objects
              .annotate(mes=TruncMonth('invoice_date'))
              .values('mes')
              .annotate(total=Sum('total')))
    ventas_map = {(r['mes'].year, r['mes'].month): float(r['total'] or 0)
                  for r in ventas if r['mes']}
    valores = [round(ventas_map.get((y, m), 0.0), 2) for (y, m) in meses]
    etiquetas = [_MESES_ABREV[m - 1] for (y, m) in meses]

    # --- Top 5 productos más vendidos (por cantidad) ---
    top = (InvoiceDetail.objects
           .values('product__name')
           .annotate(qty=Sum('quantity'))
           .order_by('-qty')[:5])
    top_products = [{'name': t['product__name'] or '—', 'qty': t['qty'] or 0} for t in top]
    max_qty = max((t['qty'] for t in top_products), default=0) or 1
    for t in top_products:
        t['pct'] = round(t['qty'] / max_qty * 100)

    # --- Donut: productos activos vs inactivos ---
    activos = Product.objects.filter(is_active=True).count()
    inactivos = Product.objects.filter(is_active=False).count()
    total_p = activos + inactivos
    r = 54
    C = round(2 * math.pi * r, 2)
    activos_len = round(C * activos / total_p, 2) if total_p else 0
    donut = {'r': r, 'C': C, 'active_len': activos_len, 'rest': round(C - activos_len, 2),
             'active': activos, 'inactive': inactivos,
             'pct': round(activos / total_p * 100) if total_p else 0}

    context = {
        'total_brands': Brand.objects.count(),
        'total_products': Product.objects.count(),
        'total_customers': Customer.objects.count(),
        'total_invoices': Invoice.objects.count(),
        'revenue': revenue,
        'inventory_value': inventory_value,
        'sales_chart': _area_chart(valores, etiquetas),
        'top_products': top_products,
        'donut': donut,
        'recent_invoices': Invoice.objects.select_related('customer')[:5],
        'low_stock': Product.objects.filter(stock__lte=5, is_active=True)[:6],
    }
    return render(request, 'billing/home.html', context)

# === BRAND (lista CBV + create/update/delete FBV con auditoría) ===
class BrandListView(ExportListMixin, PermissionRequiredMixin, ListView):
    model = Brand
    permission_required = 'billing.view_brand'
    template_name = 'billing/brand_list.html'
    context_object_name = 'items'
    paginate_by = 10
    export_title = 'Listado de Marcas'
    columns_session_key = 'brand_columns'
    export_columns = [
        {'key': 'name',        'label': 'Nombre',         'field': 'name',        'default': True},
        {'key': 'description', 'label': 'Descripción',    'field': 'description', 'default': True},
        {'key': 'is_active',   'label': 'Estado',         'field': 'is_active',   'default': True},
        {'key': 'created_at',  'label': 'Fecha creación', 'field': 'created_at',  'default': False},
        {'key': 'updated_at',  'label': 'Actualizado',    'field': 'updated_at',  'default': False},
    ]

    def get_queryset(self):
        qs = super().get_queryset()
        self.filter_form = BrandFilterForm(self.request.GET)
        self.filter_form.is_valid()
        cd = self.filter_form.cleaned_data
        if cd.get('name'):
            qs = qs.filter(name__icontains=cd['name'])
        if cd.get('is_active'):
            qs = qs.filter(is_active=(cd['is_active'] == '1'))
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['filter_form'] = self.filter_form
        return ctx

@login_required
@permission_required('billing.view_brand', raise_exception=True)
@audit_action('VIEW_BRAND')
def brand_detail(request, pk):
    brand = get_object_or_404(Brand, pk=pk)
    return render(request, 'billing/brand_detail.html', {'brand': brand})

@login_required
@permission_required('billing.add_brand', raise_exception=True)
@audit_action('CREATE_BRAND')
def brand_create(request):
    if request.method == 'POST':
        form = BrandForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'Brand created!')
            return redirect('billing:brand_list')
    else: form = BrandForm()
    return render(request, 'billing/brand_form.html', {'form':form, 'title':'Create Brand'})

@login_required
@permission_required('billing.change_brand', raise_exception=True)
@audit_action('UPDATE_BRAND')
def brand_update(request, pk):
    brand = get_object_or_404(Brand, pk=pk)
    if request.method == 'POST':
        form = BrandForm(request.POST, instance=brand)
        if form.is_valid():
            form.save()
            messages.success(request, 'Brand updated!')
            return redirect('billing:brand_list')
    else: form = BrandForm(instance=brand)
    return render(request, 'billing/brand_form.html', {'form':form, 'title':'Edit Brand'})

@login_required
@permission_required('billing.delete_brand', raise_exception=True)
@audit_action('DELETE_BRAND')
def brand_delete(request, pk):
    brand = get_object_or_404(Brand, pk=pk)
    if request.method == 'POST':
        brand.delete()
        messages.success(request, 'Brand deleted!')
        return redirect('billing:brand_list')
    return render(request, 'billing/brand_confirm_delete.html', {'object': brand})

# === PRODUCTGROUP (CBV) ===
class ProductGroupListView(ExportListMixin, PermissionRequiredMixin, ListView):
    model = ProductGroup
    permission_required = 'billing.view_productgroup'
    template_name = 'billing/productgroup_list.html'
    context_object_name = 'items'
    paginate_by = 10
    export_title = 'Listado de Categorías'
    columns_session_key = 'productgroup_columns'
    export_columns = [
        {'key': 'name',        'label': 'Nombre',         'field': 'name',        'default': True},
        {'key': 'is_active',   'label': 'Estado',         'field': 'is_active',   'default': True},
        {'key': 'created_at',  'label': 'Fecha creación', 'field': 'created_at',  'default': False},
        {'key': 'updated_at',  'label': 'Actualizado',    'field': 'updated_at',  'default': False},
    ]

    def get_queryset(self):
        qs = super().get_queryset()
        self.filter_form = ProductGroupFilterForm(self.request.GET)
        self.filter_form.is_valid()
        cd = self.filter_form.cleaned_data
        if cd.get('name'):
            qs = qs.filter(name__icontains=cd['name'])
        if cd.get('is_active'):
            qs = qs.filter(is_active=(cd['is_active'] == '1'))
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['filter_form'] = self.filter_form
        return ctx

class ProductGroupDetailView(PermissionRequiredMixin, DetailView):
    permission_required = 'billing.view_productgroup'
    model = ProductGroup; template_name = 'billing/productgroup_detail.html'; context_object_name = 'group'
class ProductGroupCreateView(PermissionRequiredMixin, CreateView):
    permission_required = 'billing.add_productgroup'
    model = ProductGroup; form_class = ProductGroupForm; template_name = 'billing/productgroup_form.html'; success_url = reverse_lazy('billing:productgroup_list')
class ProductGroupUpdateView(PermissionRequiredMixin, UpdateView):
    permission_required = 'billing.change_productgroup'
    model = ProductGroup; form_class = ProductGroupForm; template_name = 'billing/productgroup_form.html'; success_url = reverse_lazy('billing:productgroup_list')
class ProductGroupDeleteView(PermissionRequiredMixin, DeleteView):
    permission_required = 'billing.delete_productgroup'
    model = ProductGroup; template_name = 'billing/productgroup_confirm_delete.html'; success_url = reverse_lazy('billing:productgroup_list')

# === SUPPLIER (CBV) ===
class SupplierListView(ExportListMixin, PermissionRequiredMixin, ListView):
    model = Supplier
    permission_required = 'billing.view_supplier'
    template_name = 'billing/supplier_list.html'
    context_object_name = 'items'
    paginate_by = 10
    export_title = 'Listado de Proveedores'
    columns_session_key = 'supplier_columns'
    export_columns = [
        {'key': 'name',         'label': 'Empresa',        'field': 'name',         'default': True},
        {'key': 'contact_name', 'label': 'Contacto',       'field': 'contact_name', 'default': True},
        {'key': 'email',        'label': 'Email',          'field': 'email',        'default': True},
        {'key': 'phone',        'label': 'Teléfono',       'field': 'phone',        'default': True},
        {'key': 'address',      'label': 'Dirección',      'field': 'address',      'default': False},
        {'key': 'is_active',    'label': 'Estado',         'field': 'is_active',    'default': True},
        {'key': 'created_at',   'label': 'Fecha creación', 'field': 'created_at',   'default': False},
    ]

    def get_queryset(self):
        qs = super().get_queryset()
        self.filter_form = SupplierFilterForm(self.request.GET)
        self.filter_form.is_valid()
        cd = self.filter_form.cleaned_data
        if cd.get('name'):
            qs = qs.filter(name__icontains=cd['name'])
        if cd.get('contact_name'):
            qs = qs.filter(contact_name__icontains=cd['contact_name'])
        if cd.get('email'):
            qs = qs.filter(email__icontains=cd['email'])
        if cd.get('is_active'):
            qs = qs.filter(is_active=(cd['is_active'] == '1'))
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['filter_form'] = self.filter_form
        return ctx

class SupplierDetailView(PermissionRequiredMixin, DetailView):
    permission_required = 'billing.view_supplier'
    model = Supplier; template_name = 'billing/supplier_detail.html'; context_object_name = 'supplier'
class SupplierCreateView(PermissionRequiredMixin, CreateView):
    permission_required = 'billing.add_supplier'
    model = Supplier; form_class = SupplierForm; template_name = 'billing/supplier_form.html'; success_url = reverse_lazy('billing:supplier_list')
class SupplierUpdateView(PermissionRequiredMixin, UpdateView):
    permission_required = 'billing.change_supplier'
    model = Supplier; form_class = SupplierForm; template_name = 'billing/supplier_form.html'; success_url = reverse_lazy('billing:supplier_list')
class SupplierDeleteView(PermissionRequiredMixin, DeleteView):
    permission_required = 'billing.delete_supplier'
    model = Supplier; template_name = 'billing/supplier_confirm_delete.html'; success_url = reverse_lazy('billing:supplier_list')

# === PRODUCT (CBV) ===
class ProductListView(ExportListMixin, PermissionRequiredMixin, ListView):
    model = Product
    permission_required = 'billing.view_product'
    template_name = 'billing/product_list.html'
    context_object_name = 'items'
    paginate_by = 3
    export_title = 'Listado de Productos'
    columns_session_key = 'product_columns'
    # === Única fuente de configuración de columnas ===
    # La usan el listado HTML, el PDF y el Excel (mismas columnas y mismo orden).
    export_columns = [
        {'key': 'image',       'label': 'Imagen',         'field': 'image',      'default': True,  'type': 'image'},
        {'key': 'name',        'label': 'Nombre',         'field': 'name',       'default': True},
        {'key': 'description', 'label': 'Descripción',    'field': 'description','default': False},
        {'key': 'brand',       'label': 'Marca',          'field': 'brand.name', 'default': True},
        {'key': 'group',       'label': 'Grupo',          'field': 'group.name', 'default': True},
        {'key': 'unit_price',  'label': 'Precio',         'field': 'unit_price', 'default': True},
        {'key': 'stock',       'label': 'Stock',          'field': 'stock',      'default': True},
        {'key': 'balance',     'label': 'Balance',        'field': 'balance',    'default': True},
        {'key': 'suppliers',   'label': 'Proveedores',    'field': 'suppliers',  'default': True},
        {'key': 'is_active',   'label': 'Estado',         'field': 'is_active',  'default': True},
        {'key': 'created_at',  'label': 'Fecha creación', 'field': 'created_at', 'default': False},
    ]

    def get_queryset(self):
        qs = (super().get_queryset()
              .select_related('brand', 'group')
              .prefetch_related('suppliers'))
        # Bind del formulario con los parámetros GET y limpieza de datos
        self.filter_form = ProductFilterForm(self.request.GET)
        self.filter_form.is_valid()  # llena cleaned_data (campos válidos)
        cd = self.filter_form.cleaned_data
        # Búsqueda por cada columna según su tipo de dato
        if cd.get('name'):
            qs = qs.filter(name__icontains=cd['name'])
        if cd.get('brand'):
            qs = qs.filter(brand=cd['brand'])
        if cd.get('group'):
            qs = qs.filter(group=cd['group'])
        if cd.get('supplier'):
            qs = qs.filter(suppliers=cd['supplier'])
        if cd.get('price_min') is not None:
            qs = qs.filter(unit_price__gte=cd['price_min'])
        if cd.get('price_max') is not None:
            qs = qs.filter(unit_price__lte=cd['price_max'])
        if cd.get('stock_min') is not None:
            qs = qs.filter(stock__gte=cd['stock_min'])
        if cd.get('stock_max') is not None:
            qs = qs.filter(stock__lte=cd['stock_max'])
        if cd.get('is_active'):
            qs = qs.filter(is_active=(cd['is_active'] == '1'))
        # distinct() evita duplicados al filtrar por M2M (suppliers)
        return qs.distinct()

    def get_context_data(self, **kwargs):
        # 'querystring' lo aporta ExportListMixin (conserva filtros en
        # paginación y en los botones de exportar).
        ctx = super().get_context_data(**kwargs)
        ctx['filter_form'] = self.filter_form
        return ctx

class ProductDetailView(PermissionRequiredMixin, DetailView):
    permission_required = 'billing.view_product'
    model = Product
    template_name = 'billing/product_detail.html'
    context_object_name = 'product'
class ProductCreateView(PermissionRequiredMixin, CreateView):
    permission_required = 'billing.add_product'
    model = Product; form_class = ProductForm; template_name = 'billing/product_form.html'; success_url = reverse_lazy('billing:product_list')
class ProductUpdateView(PermissionRequiredMixin, UpdateView):
    permission_required = 'billing.change_product'
    model = Product; form_class = ProductForm; template_name = 'billing/product_form.html'; success_url = reverse_lazy('billing:product_list')
class ProductDeleteView(PermissionRequiredMixin, DeleteView):
    permission_required = 'billing.delete_product'
    model = Product; template_name = 'billing/product_confirm_delete.html'; success_url = reverse_lazy('billing:product_list')

# === CUSTOMER (CBV) ===
class CustomerListView(ExportListMixin, PermissionRequiredMixin, ListView):
    model = Customer
    permission_required = 'billing.view_customer'
    template_name = 'billing/customer_list.html'
    context_object_name = 'items'
    paginate_by = 10
    export_title = 'Listado de Clientes'
    columns_session_key = 'customer_columns'
    # === Única fuente de configuración de columnas (listado + PDF + Excel) ===
    export_columns = [
        {'key': 'dni',         'label': 'DNI/RUC',        'field': 'dni',        'default': True},
        {'key': 'first_name',  'label': 'Nombres',        'field': 'first_name', 'default': True},
        {'key': 'last_name',   'label': 'Apellidos',      'field': 'last_name',  'default': True},
        {'key': 'email',       'label': 'Email',          'field': 'email',      'default': True},
        {'key': 'phone',       'label': 'Teléfono',       'field': 'phone',      'default': True},
        {'key': 'address',     'label': 'Dirección',      'field': 'address',    'default': False},
        {'key': 'is_active',   'label': 'Estado',         'field': 'is_active',  'default': True},
        {'key': 'created_at',  'label': 'Fecha creación', 'field': 'created_at', 'default': False},
    ]

    def get_queryset(self):
        qs = super().get_queryset()
        self.filter_form = CustomerFilterForm(self.request.GET)
        self.filter_form.is_valid()
        cd = self.filter_form.cleaned_data
        if cd.get('dni'):
            qs = qs.filter(dni__icontains=cd['dni'])
        if cd.get('first_name'):
            qs = qs.filter(first_name__icontains=cd['first_name'])
        if cd.get('last_name'):
            qs = qs.filter(last_name__icontains=cd['last_name'])
        if cd.get('email'):
            qs = qs.filter(email__icontains=cd['email'])
        if cd.get('is_active'):
            qs = qs.filter(is_active=(cd['is_active'] == '1'))
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['filter_form'] = self.filter_form
        return ctx

class CustomerDetailView(PermissionRequiredMixin, DetailView):
    permission_required = 'billing.view_customer'
    model = Customer
    template_name = 'billing/customer_detail.html'
    context_object_name = 'customer'
class CustomerCreateView(PermissionRequiredMixin, CreateView):
    permission_required = 'billing.add_customer'
    model = Customer; form_class = CustomerForm; template_name = 'billing/customer_form.html'; success_url = reverse_lazy('billing:customer_list')
class CustomerUpdateView(PermissionRequiredMixin, UpdateView):
    permission_required = 'billing.change_customer'
    model = Customer; form_class = CustomerForm; template_name = 'billing/customer_form.html'; success_url = reverse_lazy('billing:customer_list')
class CustomerDeleteView(PermissionRequiredMixin, DeleteView):
    permission_required = 'billing.delete_customer'
    model = Customer; template_name = 'billing/customer_confirm_delete.html'; success_url = reverse_lazy('billing:customer_list')

# === INVOICE (lista CBV + create/detail/delete FBV con formset) ===
class InvoiceListView(ExportListMixin, PermissionRequiredMixin, ListView):
    model = Invoice
    permission_required = 'billing.view_invoice'
    template_name = 'billing/invoice_list.html'
    context_object_name = 'items'
    paginate_by = 10
    export_title = 'Listado de Facturas'
    columns_session_key = 'invoice_columns'
    export_columns = [
        {'key': 'id',             'label': '#',           'field': 'id',             'default': True},
        {'key': 'numero_factura', 'label': 'N.º Factura', 'field': 'numero_factura', 'default': True},
        {'key': 'customer',       'label': 'Cliente',     'field': 'customer',       'default': True},
        {'key': 'invoice_date',   'label': 'Fecha',       'field': 'invoice_date',   'default': True},
        {'key': 'total',          'label': 'Total',       'field': 'total',          'default': True},
        {'key': 'payment_status', 'label': 'Pago',        'field': 'payment_status', 'default': True},
        {'key': 'subtotal',       'label': 'Subtotal',    'field': 'subtotal',       'default': False},
        {'key': 'tax',            'label': 'IVA',         'field': 'tax',            'default': False},
        {'key': 'is_active',      'label': 'Activa',      'field': 'is_active',      'default': False},
    ]

    def get_queryset(self):
        qs = super().get_queryset().select_related('customer')
        self.filter_form = InvoiceFilterForm(self.request.GET)
        self.filter_form.is_valid()
        cd = self.filter_form.cleaned_data
        if cd.get('customer'):
            qs = qs.filter(customer=cd['customer'])
        if cd.get('date_from'):
            qs = qs.filter(invoice_date__date__gte=cd['date_from'])
        if cd.get('date_to'):
            qs = qs.filter(invoice_date__date__lte=cd['date_to'])
        if cd.get('is_active'):
            qs = qs.filter(is_active=(cd['is_active'] == '1'))
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['filter_form'] = self.filter_form
        return ctx

@login_required
@permission_required('billing.add_invoice', raise_exception=True)
def invoice_create(request):
    """Crea una factura con sus líneas de detalle (formset)."""
    if request.method == 'POST':
        form = InvoiceForm(request.POST)
        formset = InvoiceDetailFormSet(request.POST)
        if form.is_valid() and formset.is_valid():
            # Cantidad total pedida por producto (una factura puede repetir
            # el mismo producto en más de una línea).
            needed = {}
            for detail_form in formset:
                cd = detail_form.cleaned_data
                if not cd or cd.get('DELETE') or not cd.get('product'):
                    continue
                pid = cd['product'].pk
                needed[pid] = needed.get(pid, 0) + (cd.get('quantity') or 0)

            invoice = None
            with transaction.atomic():
                # select_for_update bloquea las filas de producto involucradas
                # hasta el final de la transacción: si dos ventas del mismo
                # producto llegan al mismo tiempo, la segunda espera a que la
                # primera termine y vuelve a leer el stock ya actualizado, en
                # vez de que ambas validen contra el mismo stock "viejo".
                locked = {p.pk: p for p in
                          Product.objects.select_for_update().filter(pk__in=needed)}
                stock_errors = [
                    f'Stock insuficiente para "{locked[pid].name}": '
                    f'disponible {locked[pid].stock}, solicitado {qty}.'
                    for pid, qty in needed.items() if qty > locked[pid].stock
                ]
                if stock_errors:
                    for err in stock_errors:
                        messages.error(request, err)
                else:
                    invoice = form.save(commit=False)
                    invoice.save()
                    formset.instance = invoice
                    formset.save()
                    for pid, qty in needed.items():
                        locked[pid].stock -= qty
                        locked[pid].save(update_fields=['stock'])
                    subtotal = sum((d.subtotal for d in invoice.details.all()), Decimal('0'))
                    invoice.subtotal = subtotal
                    invoice.tax = subtotal * Decimal('0.15')
                    invoice.total = invoice.subtotal + invoice.tax
                    invoice.save()

                    # Crédito de ventas: CONTADO queda cancelada al instante
                    # (sin cuotas); CREDITO genera el plan de cuotas mensuales.
                    if form.cleaned_data['tipo_pago'] == 'CREDITO':
                        generar_cuotas_venta(invoice, form.cleaned_data['num_cuotas'])
                    else:
                        invoice.tipo_pago = 'CONTADO'
                        invoice.saldo = Decimal('0')
                        invoice.estado = 'PAGADA'
                        invoice.payment_status = 'PAGADA'
                        invoice.payment_method = 'efectivo'
                        invoice.payment_date = timezone.now()
                        invoice.save(update_fields=['tipo_pago', 'saldo', 'estado',
                                                    'payment_status', 'payment_method', 'payment_date'])

                    # Facturación electrónica: asignar número + clave de acceso
                    asignar_datos_electronicos(invoice)
                    # Crear el comprobante electrónico (estado GENERADO); el
                    # usuario lo avanza por el ciclo del SRI desde el detalle.
                    generar_comprobante(invoice)

            if invoice is not None:
                send_invoice_email(invoice)  # fuera de la transacción: no retiene el lock durante el envío
                messages.success(request, f'Factura {invoice.numero_factura} creada. Total: ${invoice.total}')
                return redirect('billing:invoice_list')
    else:
        form = InvoiceForm()
        formset = InvoiceDetailFormSet()

    products_data = {
        str(p.id): {'price': str(p.unit_price), 'stock': p.stock, 'name': p.name}
        for p in Product.objects.filter(is_active=True).only('id', 'unit_price', 'stock', 'name')
    }
    return render(request, 'billing/invoice_form.html', {
        'form': form,
        'formset': formset,
        'title': 'Nueva Factura',
        'products_json': json.dumps(products_data),
    })

@login_required
@permission_required('billing.view_invoice', raise_exception=True)
def invoice_detail(request, pk):
    """Muestra el detalle completo de una factura."""
    invoice = get_object_or_404(
        Invoice.objects.select_related('customer').prefetch_related('details__product', 'payment_logs__user'),
        pk=pk,
    )
    return render(request, 'billing/invoice_detail.html', {
        'invoice': invoice,
        'paypal_configured': paypal.is_configured(),
        'comprobante': getattr(invoice, 'comprobante', None),
    })

@login_required
@permission_required('billing.view_invoice', raise_exception=True)
def invoice_pdf(request, pk):
    """Descarga el PDF (comprobante) de la factura electrónica."""
    invoice = get_object_or_404(
        Invoice.objects.select_related('customer').prefetch_related('details__product'), pk=pk)
    return invoice_pdf_response(invoice)


def _apply_payment(invoice, user, method, note=''):
    """Marca la factura como PAGADA, registra la bitácora (PaymentLog) y
    reenvía el comprobante por correo. Común a pago manual y PayPal."""
    invoice.payment_status = 'PAGADA'
    invoice.payment_method = method
    invoice.payment_date = timezone.now()
    invoice.save(update_fields=['payment_status', 'payment_method', 'payment_date'])
    PaymentLog.objects.create(
        invoice=invoice, user=user, method=method, amount=invoice.total, note=note[:200],
    )
    send_invoice_email(invoice)  # reenvía el comprobante (ahora PAGADA) con el PDF


@login_required
@permission_required('billing.change_invoice', raise_exception=True)
def invoice_mark_paid(request, pk):
    """Marca una factura como PAGADA con un método manual (efectivo,
    transferencia, tarjeta). Solo por POST."""
    invoice = get_object_or_404(Invoice, pk=pk)
    if request.method != 'POST':
        return redirect('billing:invoice_detail', pk=pk)
    if invoice.payment_status == 'PAGADA':
        messages.info(request, f'La factura {invoice.numero_factura} ya estaba pagada.')
        return redirect('billing:invoice_detail', pk=pk)

    method = request.POST.get('payment_method')
    valid_methods = dict(Invoice.PAYMENT_METHOD)
    if method not in valid_methods or method == 'paypal':
        messages.error(request, 'Selecciona un método de pago válido.')
        return redirect('billing:invoice_detail', pk=pk)

    _apply_payment(invoice, request.user, method, note=request.POST.get('note', ''))
    messages.success(request, f'Factura {invoice.numero_factura} marcada como pagada ({valid_methods[method]}).')
    return redirect('billing:invoice_detail', pk=pk)


@login_required
@permission_required('billing.change_invoice', raise_exception=True)
def invoice_paypal_start(request, pk):
    """Crea la orden en PayPal (Sandbox) y redirige al usuario a aprobarla."""
    invoice = get_object_or_404(Invoice, pk=pk)
    if request.method != 'POST':
        return redirect('billing:invoice_detail', pk=pk)
    if invoice.payment_status == 'PAGADA':
        messages.info(request, f'La factura {invoice.numero_factura} ya estaba pagada.')
        return redirect('billing:invoice_detail', pk=pk)
    if not paypal.is_configured():
        messages.error(request, 'PayPal no está configurado en este servidor todavía.')
        return redirect('billing:invoice_detail', pk=pk)

    try:
        order_id, approve_url = paypal.create_order(invoice, request)
    except paypal.PayPalError as exc:
        messages.error(request, str(exc))
        return redirect('billing:invoice_detail', pk=pk)

    request.session[f'paypal_order_{invoice.pk}'] = order_id
    return redirect(approve_url)


@login_required
@permission_required('billing.change_invoice', raise_exception=True)
def invoice_paypal_return(request, pk):
    """PayPal redirige aquí tras la aprobación del usuario; se captura el pago."""
    invoice = get_object_or_404(Invoice, pk=pk)
    order_id = request.GET.get('token') or request.session.get(f'paypal_order_{invoice.pk}')
    if invoice.payment_status == 'PAGADA':
        messages.info(request, f'La factura {invoice.numero_factura} ya estaba pagada.')
        return redirect('billing:invoice_detail', pk=pk)
    if not order_id:
        messages.error(request, 'No se recibió la orden de PayPal.')
        return redirect('billing:invoice_detail', pk=pk)

    try:
        status, capture_id = paypal.capture_order(order_id)
    except paypal.PayPalError as exc:
        messages.error(request, str(exc))
        return redirect('billing:invoice_detail', pk=pk)

    if status != 'COMPLETED':
        messages.error(request, f'PayPal no completó el pago (estado: {status}).')
        return redirect('billing:invoice_detail', pk=pk)

    _apply_payment(invoice, request.user, 'paypal',
                   note=f'PayPal order {order_id} / capture {capture_id}')
    request.session.pop(f'paypal_order_{invoice.pk}', None)
    messages.success(request, f'Pago con PayPal confirmado para la factura {invoice.numero_factura}.')
    return redirect('billing:invoice_detail', pk=pk)


@login_required
@permission_required('billing.change_invoice', raise_exception=True)
def invoice_paypal_cancel(request, pk):
    """El usuario canceló el pago en PayPal: no se toca la factura."""
    invoice = get_object_or_404(Invoice, pk=pk)
    request.session.pop(f'paypal_order_{invoice.pk}', None)
    messages.info(request, 'Pago con PayPal cancelado. La factura sigue pendiente.')
    return redirect('billing:invoice_detail', pk=pk)


@login_required
@permission_required('billing.delete_invoice', raise_exception=True)
def invoice_delete(request, pk):
    """Elimina una factura y sus detalles (CASCADE)."""
    invoice = get_object_or_404(Invoice, pk=pk)
    if request.method == 'POST':
        invoice_id = invoice.id
        invoice.delete()
        messages.success(request, f'Invoice #{invoice_id} deleted!')
        return redirect('billing:invoice_list')
    return render(request, 'billing/invoice_confirm_delete.html', {'object': invoice})
