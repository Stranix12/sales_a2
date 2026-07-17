from django.db import models
from django.core.validators import MinValueValidator
from decimal import Decimal
from billing.models import Supplier, Product, Invoice   # Reutilizamos modelos de billing
 
 
class Purchase(models.Model):
    """Cabecera de compra. Documenta una adquisición a un proveedor."""
    # --- Compras a crédito (app creditos_compras) — mismos choices que
    # billing.Invoice, importados para no duplicar la tupla.
    TIPO_PAGO = Invoice.TIPO_PAGO
    ESTADO_CREDITO = Invoice.ESTADO_CREDITO

    supplier = models.ForeignKey(
        Supplier, on_delete=models.PROTECT, related_name='purchases'
    )
    document_number = models.CharField(
        max_length=20, verbose_name='N.º de factura del proveedor'
    )
    purchase_date = models.DateTimeField(auto_now_add=True)
    subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    tax = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    is_active = models.BooleanField(default=True)
    tipo_pago = models.CharField(max_length=10, choices=TIPO_PAGO, default='CONTADO')
    saldo = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    estado = models.CharField(max_length=15, choices=ESTADO_CREDITO, default='PENDIENTE')
 
    class Meta:
        verbose_name = 'Compra'
        verbose_name_plural = 'Compras'
        ordering = ['-purchase_date']
        permissions = [
            ('view_purchase_report', 'Puede ver el reporte de costo promedio'),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['supplier', 'document_number'],
                name='unique_supplier_document_number',
            )
        ]
 
    def __str__(self):
        return f'Purchase #{self.id} - {self.supplier}'
 
 
class PurchaseDetail(models.Model):
    """Líneas de compra. Cada fila es un producto adquirido."""
    purchase = models.ForeignKey(
        Purchase, on_delete=models.CASCADE, related_name='details'
    )
    product = models.ForeignKey(
        Product, on_delete=models.PROTECT, related_name='purchase_details'
    )
    quantity = models.PositiveIntegerField(default=1, validators=[MinValueValidator(1)])
    unit_cost = models.DecimalField(
        max_digits=12, decimal_places=2, validators=[MinValueValidator(Decimal('0.01'))]
    )
    subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    class Meta:
        verbose_name = 'Detalle de compra'
        verbose_name_plural = 'Detalles de compra'

    def __str__(self):
        return f'{self.product.name} x {self.quantity}'

    def save(self, *args, **kwargs):
        self.subtotal = self.quantity * self.unit_cost
        super().save(*args, **kwargs)
