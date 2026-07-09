from decimal import Decimal, ROUND_HALF_UP
from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from shared.validators import validate_cedula_ec

class Brand(models.Model):
    """Marcas de productos."""
    name = models.CharField(max_length=100, unique=True, verbose_name='NombreMarca')
    description = models.TextField(blank=True, null=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    class Meta:
        verbose_name = 'Brand'
        verbose_name_plural = 'Brands'
        ordering = ['name']
    def __str__(self): return self.name

class ProductGroup(models.Model):
    """Grupos/categorías de productos."""
    name = models.CharField(max_length=100, unique=True, verbose_name='Group Name')
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    class Meta:
        verbose_name = 'Product Group'
        verbose_name_plural = 'Product Groups'
        ordering = ['name']
    def __str__(self): return self.name

class Supplier(models.Model):
    """Proveedores. M2M con Product."""
    name = models.CharField(max_length=200, verbose_name='Company Name')
    contact_name = models.CharField(max_length=200, blank=True, null=True)
    email = models.EmailField(blank=True, null=True)
    phone = models.CharField(max_length=20, blank=True, null=True)
    address = models.TextField(blank=True, null=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    class Meta:
        verbose_name = 'Supplier'
        verbose_name_plural = 'Suppliers'
        ordering = ['name']
    def __str__(self): return self.name

class Product(models.Model):
    """Productos. FK a Brand/Group, M2M a Supplier."""
    name = models.CharField(max_length=200, verbose_name='Product Name')
    description = models.TextField(blank=True, null=True)
    image = models.ImageField(upload_to='products/', blank=True, null=True, verbose_name='Image')
    brand = models.ForeignKey(Brand, on_delete=models.PROTECT, related_name='products')
    group = models.ForeignKey(ProductGroup, on_delete=models.PROTECT, related_name='products')
    suppliers = models.ManyToManyField(Supplier, related_name='products', blank=True)
    unit_price = models.DecimalField(max_digits=12, decimal_places=2,
                                     validators=[MinValueValidator(Decimal('0.01'))])
    stock = models.IntegerField(default=0, validators=[MinValueValidator(0)])
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    class Meta:
        verbose_name = 'Product'
        verbose_name_plural = 'Products'
        ordering = ['name']
    def __str__(self): return f'{self.name} ({self.brand.name})'
    @property
    def balance(self):
        """Valor total en inventario: precio unitario × stock.

        Se calcula dinámicamente (no se almacena en BD) y se redondea a 2
        decimales según la configuración monetaria."""
        price = self.unit_price or Decimal('0')
        return (price * (self.stock or 0)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

class Customer(models.Model):
    """Clientes. OneToOne con CustomerProfile."""
    # Cuenta de acceso al portal (rol "Cliente"): un usuario puede estar
    # vinculado a lo sumo a un cliente, y viceversa. Nullable porque la
    # mayoría de los clientes son solo registros (no tienen login).
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
                                null=True, blank=True, related_name='customer_account',
                                verbose_name='Usuario del portal')
    dni = models.CharField(max_length=13, unique=True, verbose_name='DNI/RUC',
                           validators=[validate_cedula_ec])
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    email = models.EmailField(blank=True, null=True)
    phone = models.CharField(max_length=20, blank=True, null=True)
    address = models.TextField(blank=True, null=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    class Meta:
        ordering = ['last_name', 'first_name']
    def __str__(self): return f'{self.last_name}, {self.first_name}'
    @property
    def full_name(self): return f'{self.first_name} {self.last_name}'

class CustomerProfile(models.Model):
    """Perfil extendido. OneToOne con Customer."""
    TAXPAYER = [('final','Final Consumer'),('ruc','RUC'),('rise','RISE')]
    PAYMENT = [('cash','Cash'),('credit_15','15 days'),('credit_30','30 days'),('credit_60','60 days')]
    customer = models.OneToOneField(Customer, on_delete=models.CASCADE, related_name='profile')
    taxpayer_type = models.CharField(max_length=10, choices=TAXPAYER, default='final')
    payment_terms = models.CharField(max_length=15, choices=PAYMENT, default='cash')
    credit_limit = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    notes = models.TextField(blank=True, null=True)
    class Meta: verbose_name = 'Customer Profile'
    def __str__(self): return f'Profile: {self.customer}'

class Invoice(models.Model):
    """Cabecera de factura (con datos de facturación electrónica simulada)."""
    PAYMENT_STATUS = [
        ('PENDIENTE', 'Pendiente'),
        ('PAGADA', 'Pagada'),
        ('ANULADA', 'Anulada'),
    ]
    PAYMENT_METHOD = [
        ('efectivo', 'Efectivo'),
        ('transferencia', 'Transferencia'),
        ('tarjeta', 'Tarjeta'),
        ('paypal', 'PayPal'),
    ]
    customer = models.ForeignKey(Customer, on_delete=models.PROTECT, related_name='invoices')
    invoice_date = models.DateTimeField(auto_now_add=True)
    subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    tax = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    is_active = models.BooleanField(default=True)
    # --- Facturación electrónica (simulada, sin conexión real al SRI) ---
    numero_factura = models.CharField(max_length=20, unique=True, blank=True, null=True,
                                      verbose_name='N.º de factura')
    clave_acceso = models.CharField(max_length=49, blank=True, null=True,
                                    verbose_name='Clave de acceso')
    payment_status = models.CharField(max_length=10, choices=PAYMENT_STATUS, default='PENDIENTE',
                                      verbose_name='Estado de pago')
    payment_method = models.CharField(max_length=15, choices=PAYMENT_METHOD, blank=True, null=True,
                                      verbose_name='Método de pago')
    payment_date = models.DateTimeField(blank=True, null=True, verbose_name='Fecha de pago')
    class Meta: ordering = ['-invoice_date']
    def __str__(self): return f'Invoice #{self.id} - {self.customer}'

    @property
    def is_paid(self):
        return self.payment_status == 'PAGADA'


class PaymentLog(models.Model):
    """Bitácora de pagos: registra cada vez que se marca una factura como
    pagada (quién, cuándo, con qué método y monto), para auditoría."""
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name='payment_logs')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                             related_name='payment_logs')
    method = models.CharField(max_length=15, choices=Invoice.PAYMENT_METHOD)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    note = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Payment Log'
    def __str__(self): return f'Pago factura #{self.invoice_id} ({self.method}) ${self.amount}'

class InvoiceDetail(models.Model):
    """Líneas de factura."""
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name='details')
    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name='invoice_details')
    quantity = models.IntegerField(default=1, validators=[MinValueValidator(1)])
    unit_price = models.DecimalField(max_digits=12, decimal_places=2,
                                     validators=[MinValueValidator(Decimal('0.01'))])
    subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    def __str__(self): return f'{self.product.name} x {self.quantity}'
    def save(self, *args, **kwargs):
        self.subtotal = self.quantity * self.unit_price
        super().save(*args, **kwargs)

# Create your models here.
