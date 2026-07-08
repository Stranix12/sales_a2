from django import forms
from django.forms import inlineformset_factory
from .models import Brand, ProductGroup, Supplier, Product, Customer, Invoice, InvoiceDetail

class BrandForm(forms.ModelForm):
    class Meta:
        model = Brand
        fields = ['name', 'description', 'is_active']
        labels = {'name': 'Nombre', 'description': 'Descripción', 'is_active': 'Activo'}
        help_texts = {'name': 'Nombre de la marca (único).'}
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ej: Isabel'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3,
                                                 'placeholder': 'Descripción de la marca...'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input', 'role': 'switch'}),
        }
        error_messages = {'name': {'required': 'El nombre es obligatorio.',
                                   'unique': 'Ya existe una marca con este nombre.'}}


class ProductFilterForm(forms.Form):
    """Filtros de búsqueda del listado de productos.

    Cada columna de la consulta tiene su control según el tipo de dato:
      - Texto  -> input de texto (búsqueda parcial)
      - FK/M2M -> select desplegable
      - Numérico (precio/stock) -> rango min/max con inputs numéricos
      - Booleano (estado) -> select Todos/Activo/Inactivo
    Todos los campos son opcionales (required=False) porque son filtros.
    """
    ACTIVE_CHOICES = [('', 'All'), ('1', 'Active'), ('0', 'Inactive')]

    name = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Search name...'}),
    )
    brand = forms.ModelChoiceField(
        queryset=Brand.objects.all(), required=False, empty_label='All brands',
        widget=forms.Select(attrs={'class': 'form-select'}),
    )
    group = forms.ModelChoiceField(
        queryset=ProductGroup.objects.all(), required=False, empty_label='All groups',
        widget=forms.Select(attrs={'class': 'form-select'}),
    )
    supplier = forms.ModelChoiceField(
        queryset=Supplier.objects.all(), required=False, empty_label='All suppliers',
        widget=forms.Select(attrs={'class': 'form-select'}),
    )
    price_min = forms.DecimalField(
        required=False, min_value=0,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'placeholder': 'Min'}),
    )
    price_max = forms.DecimalField(
        required=False, min_value=0,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'placeholder': 'Max'}),
    )
    stock_min = forms.IntegerField(
        required=False,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'Min'}),
    )
    stock_max = forms.IntegerField(
        required=False,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'Max'}),
    )
    is_active = forms.ChoiceField(
        required=False, choices=ACTIVE_CHOICES,
        widget=forms.Select(attrs={'class': 'form-select'}),
    )

    def clean(self):
        """Valida que el mínimo no supere al máximo en los rangos."""
        cd = super().clean()
        pmin, pmax = cd.get('price_min'), cd.get('price_max')
        if pmin is not None and pmax is not None and pmin > pmax:
            self.add_error('price_max', 'Max price must be greater than or equal to min price.')
        smin, smax = cd.get('stock_min'), cd.get('stock_max')
        if smin is not None and smax is not None and smin > smax:
            self.add_error('stock_max', 'Max stock must be greater than or equal to min stock.')
        return cd


class ProductForm(forms.ModelForm):
    """Formulario de creación y edición de productos.

    Centraliza widgets, estilos Bootstrap, placeholders, help_text, mensajes de
    error y validaciones. Lo usan ProductCreateView y ProductUpdateView (sin
    configuración del formulario en las vistas).
    """
    class Meta:
        model = Product
        fields = ['name', 'description', 'image', 'brand', 'group',
                  'suppliers', 'unit_price', 'stock', 'is_active']
        labels = {
            'name': 'Nombre',
            'description': 'Descripción',
            'image': 'Imagen',
            'brand': 'Marca',
            'group': 'Categoría',
            'suppliers': 'Proveedores',
            'unit_price': 'Precio unitario',
            'stock': 'Stock',
            'is_active': 'Activo',
        }
        help_texts = {
            'name': 'Nombre comercial del producto.',
            'unit_price': 'Valor por unidad. Debe ser mayor que cero.',
            'stock': 'Cantidad disponible en inventario.',
            'suppliers': 'Mantén pulsado Ctrl para seleccionar varios.',
        }
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-control', 'placeholder': 'Ej: Atún en lata 180g'}),
            'description': forms.Textarea(attrs={
                'class': 'form-control', 'rows': 3,
                'placeholder': 'Descripción breve del producto...'}),
            'image': forms.ClearableFileInput(attrs={
                'class': 'form-control', 'accept': 'image/*', 'id': 'id_image'}),
            'brand': forms.Select(attrs={'class': 'form-select'}),
            'group': forms.Select(attrs={'class': 'form-select'}),
            'suppliers': forms.SelectMultiple(attrs={'class': 'form-select', 'size': 4}),
            'unit_price': forms.NumberInput(attrs={
                'class': 'form-control', 'min': '0.01', 'step': '0.01',
                'placeholder': '0.00', 'id': 'id_unit_price'}),
            'stock': forms.NumberInput(attrs={
                'class': 'form-control', 'min': '0', 'step': '1',
                'placeholder': '0', 'id': 'id_stock'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input', 'role': 'switch'}),
        }
        error_messages = {
            'name': {'required': 'El nombre es obligatorio.'},
            'brand': {'required': 'Selecciona una marca.'},
            'group': {'required': 'Selecciona una categoría.'},
            'unit_price': {
                'required': 'El precio unitario es obligatorio.',
                'invalid': 'Ingresa un valor numérico válido.'},
            'stock': {'invalid': 'Ingresa un número entero válido.'},
        }

    def clean_unit_price(self):
        """El precio debe ser numérico y estrictamente mayor que cero."""
        price = self.cleaned_data.get('unit_price')
        if price is None or price <= 0:
            raise forms.ValidationError('El precio unitario debe ser mayor que cero.')
        return price

    def clean_stock(self):
        """El stock no puede ser negativo."""
        stock = self.cleaned_data.get('stock')
        if stock is not None and stock < 0:
            raise forms.ValidationError('El stock no puede ser negativo.')
        return stock


class CustomerFilterForm(forms.Form):
    """Filtros de búsqueda del listado de clientes (un control por columna)."""
    ACTIVE_CHOICES = [('', 'All'), ('1', 'Active'), ('0', 'Inactive')]

    dni = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'DNI/RUC...'}))
    first_name = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Nombres...'}))
    last_name = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Apellidos...'}))
    email = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Email...'}))
    is_active = forms.ChoiceField(
        required=False, choices=ACTIVE_CHOICES,
        widget=forms.Select(attrs={'class': 'form-select'}))


class CustomerForm(forms.ModelForm):
    """Formulario de creación y edición de clientes.

    Centraliza widgets, estilos Bootstrap, placeholders, help_text, mensajes de
    error y validaciones. Lo usan CustomerCreateView y CustomerUpdateView.
    """
    class Meta:
        model = Customer
        fields = ['dni', 'first_name', 'last_name', 'email', 'phone', 'address', 'is_active']
        labels = {
            'dni': 'DNI/RUC',
            'first_name': 'Nombres',
            'last_name': 'Apellidos',
            'email': 'Correo electrónico',
            'phone': 'Teléfono',
            'address': 'Dirección',
            'is_active': 'Activo',
        }
        help_texts = {
            'dni': 'Cédula (10 dígitos) o RUC (13 dígitos).',
            'email': 'Opcional. Se usará para enviar facturas y notificaciones.',
        }
        widgets = {
            'dni': forms.TextInput(attrs={
                'class': 'form-control', 'placeholder': '0102030405', 'maxlength': 13,
                'inputmode': 'numeric', 'id': 'id_dni'}),
            'first_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ej: Juan Carlos'}),
            'last_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ej: Pérez López'}),
            'email': forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'cliente@correo.com'}),
            'phone': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '0991234567'}),
            'address': forms.Textarea(attrs={
                'class': 'form-control', 'rows': 3, 'placeholder': 'Dirección de domicilio o empresa...'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input', 'role': 'switch'}),
        }
        error_messages = {
            'dni': {
                'required': 'El DNI/RUC es obligatorio.',
                'unique': 'Ya existe un cliente con este DNI/RUC.'},
            'first_name': {'required': 'Los nombres son obligatorios.'},
            'last_name': {'required': 'Los apellidos son obligatorios.'},
            'email': {'invalid': 'Ingresa un correo electrónico válido.'},
        }
        # La validación del DNI/RUC (formato + algoritmo del Registro Civil) la
        # aporta validate_cedula_ec en el modelo (shared/validators.py).


class InvoiceForm(forms.ModelForm):
    """Formulario para la cabecera de la factura."""
    class Meta:
        model = Invoice
        fields = ['customer']
        widgets = {
            'customer': forms.Select(attrs={'class': 'form-select'}),
        }


# Formset: permite agregar MÚLTIPLES detalles dentro de UNA factura.
InvoiceDetailFormSet = inlineformset_factory(
    Invoice,            # modelo padre
    InvoiceDetail,      # modelo hijo
    fields=['product', 'quantity', 'unit_price'],
    extra=3,            # 3 filas vacías para agregar
    can_delete=True,    # checkbox para eliminar filas
    widgets={
        'product': forms.Select(attrs={'class': 'form-select'}),
        'quantity': forms.NumberInput(attrs={'class': 'form-control', 'min': 1}),
        'unit_price': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0.01'}),
    },
)


# =====================================================================
#  FILTROS Y FORMULARIOS: Brand / ProductGroup / Supplier / Invoice
# =====================================================================
ACTIVE_CHOICES = [('', 'All'), ('1', 'Active'), ('0', 'Inactive')]


class BrandFilterForm(forms.Form):
    """Filtros del listado de marcas."""
    name = forms.CharField(required=False,
                           widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Nombre...'}))
    is_active = forms.ChoiceField(required=False, choices=ACTIVE_CHOICES,
                                  widget=forms.Select(attrs={'class': 'form-select'}))


class ProductGroupForm(forms.ModelForm):
    """Formulario de creación/edición de categorías (grupos)."""
    class Meta:
        model = ProductGroup
        fields = ['name', 'is_active']
        labels = {'name': 'Nombre', 'is_active': 'Activo'}
        help_texts = {'name': 'Nombre de la categoría (único).'}
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ej: Embutidos'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input', 'role': 'switch'}),
        }
        error_messages = {'name': {'required': 'El nombre es obligatorio.',
                                   'unique': 'Ya existe una categoría con este nombre.'}}


class ProductGroupFilterForm(forms.Form):
    """Filtros del listado de categorías."""
    name = forms.CharField(required=False,
                           widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Nombre...'}))
    is_active = forms.ChoiceField(required=False, choices=ACTIVE_CHOICES,
                                  widget=forms.Select(attrs={'class': 'form-select'}))


class SupplierForm(forms.ModelForm):
    """Formulario de creación/edición de proveedores."""
    class Meta:
        model = Supplier
        fields = ['name', 'contact_name', 'email', 'phone', 'address', 'is_active']
        labels = {
            'name': 'Empresa', 'contact_name': 'Persona de contacto',
            'email': 'Correo electrónico', 'phone': 'Teléfono',
            'address': 'Dirección', 'is_active': 'Activo',
        }
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ej: TechDist S.A.'}),
            'contact_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ej: María Ruiz'}),
            'email': forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'proveedor@correo.com'}),
            'phone': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '0991234567'}),
            'address': forms.Textarea(attrs={'class': 'form-control', 'rows': 3,
                                             'placeholder': 'Dirección de la empresa...'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input', 'role': 'switch'}),
        }
        error_messages = {
            'name': {'required': 'El nombre de la empresa es obligatorio.'},
            'email': {'invalid': 'Ingresa un correo electrónico válido.'},
        }


class SupplierFilterForm(forms.Form):
    """Filtros del listado de proveedores."""
    name = forms.CharField(required=False,
                           widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Empresa...'}))
    contact_name = forms.CharField(required=False,
                                   widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Contacto...'}))
    email = forms.CharField(required=False,
                            widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Email...'}))
    is_active = forms.ChoiceField(required=False, choices=ACTIVE_CHOICES,
                                  widget=forms.Select(attrs={'class': 'form-select'}))


class InvoiceFilterForm(forms.Form):
    """Filtros del listado de facturas."""
    customer = forms.ModelChoiceField(
        queryset=Customer.objects.all(), required=False, empty_label='Todos los clientes',
        widget=forms.Select(attrs={'class': 'form-select'}))
    date_from = forms.DateField(required=False,
                                widget=forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}))
    date_to = forms.DateField(required=False,
                              widget=forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}))
    is_active = forms.ChoiceField(required=False, choices=ACTIVE_CHOICES,
                                  widget=forms.Select(attrs={'class': 'form-select'}))
