import json
from decimal import Decimal
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import ListView, CreateView, UpdateView, DeleteView, DetailView
from django.urls import reverse_lazy
from django.contrib.auth import login
from .models import *
from .forms import (SignUpForm, BrandForm, BrandFilterForm, ProductFilterForm, ProductForm,
                    CustomerForm, CustomerFilterForm, InvoiceForm, InvoiceDetailFormSet,
                    ProductGroupForm, ProductGroupFilterForm, SupplierForm, SupplierFilterForm,
                    InvoiceFilterForm)
from .mixins import ExportListMixin
from shared.mixins import StaffRequiredMixin
from shared.decorators import audit_action
from shared.emails import send_invoice_email


# === HOME (Página principal / Dashboard) ===
@login_required
def home(request):
    """Vista principal del sistema. Muestra un resumen general."""
    context = {
        'total_brands': Brand.objects.count(),
        'total_products': Product.objects.count(),
        'total_customers': Customer.objects.count(),
        'total_invoices': Invoice.objects.count(),
        'recent_invoices': Invoice.objects.select_related('customer')[:5],
        'low_stock': Product.objects.filter(stock__lte=5, is_active=True),
    }
    return render(request, 'billing/home.html', context)

# === REGISTRO ===
class SignUpView(CreateView):
    form_class = SignUpForm
    template_name = 'registration/signup.html'
    success_url = reverse_lazy('billing:brand_list')
    def form_valid(self, form):
        response = super().form_valid(form)
        login(self.request, self.object)
        return response

# === BRAND (lista CBV + create/update/delete FBV con auditoría) ===
class BrandListView(ExportListMixin, LoginRequiredMixin, ListView):
    model = Brand
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
@audit_action('VIEW_BRAND')
def brand_detail(request, pk):
    brand = get_object_or_404(Brand, pk=pk)
    return render(request, 'billing/brand_detail.html', {'brand': brand})

@login_required
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
@audit_action('DELETE_BRAND')
def brand_delete(request, pk):
    if not request.user.is_staff:
        messages.error(request, 'No tienes permiso para eliminar. Se requiere acceso de staff.')
        return redirect('billing:brand_list')
    brand = get_object_or_404(Brand, pk=pk)
    if request.method == 'POST':
        brand.delete()
        messages.success(request, 'Brand deleted!')
        return redirect('billing:brand_list')
    return render(request, 'billing/brand_confirm_delete.html', {'object': brand})

# === PRODUCTGROUP (CBV) ===
class ProductGroupListView(ExportListMixin, LoginRequiredMixin, ListView):
    model = ProductGroup
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

class ProductGroupDetailView(LoginRequiredMixin, DetailView):
    model = ProductGroup; template_name = 'billing/productgroup_detail.html'; context_object_name = 'group'
class ProductGroupCreateView(LoginRequiredMixin, CreateView):
    model = ProductGroup; form_class = ProductGroupForm; template_name = 'billing/productgroup_form.html'; success_url = reverse_lazy('billing:productgroup_list')
class ProductGroupUpdateView(LoginRequiredMixin, UpdateView):
    model = ProductGroup; form_class = ProductGroupForm; template_name = 'billing/productgroup_form.html'; success_url = reverse_lazy('billing:productgroup_list')
class ProductGroupDeleteView(LoginRequiredMixin, StaffRequiredMixin, DeleteView):
    model = ProductGroup; template_name = 'billing/productgroup_confirm_delete.html'; success_url = reverse_lazy('billing:productgroup_list'); staff_redirect_url = '/groups/'

# === SUPPLIER (CBV) ===
class SupplierListView(ExportListMixin, LoginRequiredMixin, ListView):
    model = Supplier
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

class SupplierDetailView(LoginRequiredMixin, DetailView):
    model = Supplier; template_name = 'billing/supplier_detail.html'; context_object_name = 'supplier'
class SupplierCreateView(LoginRequiredMixin, CreateView):
    model = Supplier; form_class = SupplierForm; template_name = 'billing/supplier_form.html'; success_url = reverse_lazy('billing:supplier_list')
class SupplierUpdateView(LoginRequiredMixin, UpdateView):
    model = Supplier; form_class = SupplierForm; template_name = 'billing/supplier_form.html'; success_url = reverse_lazy('billing:supplier_list')
class SupplierDeleteView(LoginRequiredMixin, StaffRequiredMixin, DeleteView):
    model = Supplier; template_name = 'billing/supplier_confirm_delete.html'; success_url = reverse_lazy('billing:supplier_list'); staff_redirect_url = '/suppliers/'

# === PRODUCT (CBV) ===
class ProductListView(ExportListMixin, LoginRequiredMixin, ListView):
    model = Product
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

class ProductDetailView(LoginRequiredMixin, DetailView):
    model = Product
    template_name = 'billing/product_detail.html'
    context_object_name = 'product'
class ProductCreateView(LoginRequiredMixin, CreateView):
    model = Product; form_class = ProductForm; template_name = 'billing/product_form.html'; success_url = reverse_lazy('billing:product_list')
class ProductUpdateView(LoginRequiredMixin, UpdateView):
    model = Product; form_class = ProductForm; template_name = 'billing/product_form.html'; success_url = reverse_lazy('billing:product_list')
class ProductDeleteView(LoginRequiredMixin, StaffRequiredMixin, DeleteView):
    model = Product; template_name = 'billing/product_confirm_delete.html'; success_url = reverse_lazy('billing:product_list'); staff_redirect_url = '/products/'

# === CUSTOMER (CBV) ===
class CustomerListView(ExportListMixin, LoginRequiredMixin, ListView):
    model = Customer
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

class CustomerDetailView(LoginRequiredMixin, DetailView):
    model = Customer
    template_name = 'billing/customer_detail.html'
    context_object_name = 'customer'
class CustomerCreateView(LoginRequiredMixin, CreateView):
    model = Customer; form_class = CustomerForm; template_name = 'billing/customer_form.html'; success_url = reverse_lazy('billing:customer_list')
class CustomerUpdateView(LoginRequiredMixin, UpdateView):
    model = Customer; form_class = CustomerForm; template_name = 'billing/customer_form.html'; success_url = reverse_lazy('billing:customer_list')
class CustomerDeleteView(LoginRequiredMixin, StaffRequiredMixin, DeleteView):
    model = Customer; template_name = 'billing/customer_confirm_delete.html'; success_url = reverse_lazy('billing:customer_list'); staff_redirect_url = '/customers/'

# === INVOICE (lista CBV + create/detail/delete FBV con formset) ===
class InvoiceListView(ExportListMixin, LoginRequiredMixin, ListView):
    model = Invoice
    template_name = 'billing/invoice_list.html'
    context_object_name = 'items'
    paginate_by = 10
    export_title = 'Listado de Facturas'
    columns_session_key = 'invoice_columns'
    export_columns = [
        {'key': 'id',           'label': '#',        'field': 'id',           'default': True},
        {'key': 'customer',     'label': 'Cliente',  'field': 'customer',     'default': True},
        {'key': 'invoice_date', 'label': 'Fecha',    'field': 'invoice_date', 'default': True},
        {'key': 'subtotal',     'label': 'Subtotal', 'field': 'subtotal',     'default': True},
        {'key': 'tax',          'label': 'IVA',      'field': 'tax',          'default': True},
        {'key': 'total',        'label': 'Total',    'field': 'total',        'default': True},
        {'key': 'is_active',    'label': 'Estado',   'field': 'is_active',    'default': False},
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
def invoice_create(request):
    """Crea una factura con sus líneas de detalle (formset)."""
    if request.method == 'POST':
        form = InvoiceForm(request.POST)
        formset = InvoiceDetailFormSet(request.POST)
        if form.is_valid() and formset.is_valid():
            # Validar stock antes de guardar
            stock_errors = []
            for detail_form in formset:
                cd = detail_form.cleaned_data
                if not cd or cd.get('DELETE'):
                    continue
                product = cd.get('product')
                qty = cd.get('quantity') or 0
                if product and qty > product.stock:
                    stock_errors.append(
                        f'Stock insuficiente para "{product.name}": '
                        f'disponible {product.stock}, solicitado {qty}.'
                    )
            if stock_errors:
                for err in stock_errors:
                    messages.error(request, err)
            else:
                invoice = form.save(commit=False)
                invoice.save()
                formset.instance = invoice
                saved_details = formset.save()
                # Descontar stock de cada producto facturado
                for detail in saved_details:
                    p = detail.product
                    p.stock -= detail.quantity
                    p.save(update_fields=['stock'])
                subtotal = sum((d.subtotal for d in invoice.details.all()), Decimal('0'))
                invoice.subtotal = subtotal
                invoice.tax = subtotal * Decimal('0.15')
                invoice.total = invoice.subtotal + invoice.tax
                invoice.save()
                send_invoice_email(invoice)
                messages.success(request, f'Factura #{invoice.id} creada. Total: ${invoice.total}')
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
def invoice_detail(request, pk):
    """Muestra el detalle completo de una factura."""
    invoice = get_object_or_404(
        Invoice.objects.select_related('customer').prefetch_related('details__product'),
        pk=pk,
    )
    return render(request, 'billing/invoice_detail.html', {'invoice': invoice})

@login_required
def invoice_delete(request, pk):
    """Elimina una factura y sus detalles (CASCADE). Solo staff."""
    if not request.user.is_staff:
        messages.error(request, 'No tienes permiso para eliminar facturas. Se requiere acceso de staff.')
        return redirect('billing:invoice_list')
    invoice = get_object_or_404(Invoice, pk=pk)
    if request.method == 'POST':
        invoice_id = invoice.id
        invoice.delete()
        messages.success(request, f'Invoice #{invoice_id} deleted!')
        return redirect('billing:invoice_list')
    return render(request, 'billing/invoice_confirm_delete.html', {'object': invoice})
