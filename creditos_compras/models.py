"""Compras a crédito con plan de pagos (caso de estudio creditos_compras).

Estos modelos vivían originalmente en creditos_ventas (que cubría ventas y
compras); el caso de estudio pide una app propia para el crédito de compras,
así que se trasladaron aquí. La migración 0001 conserva las tablas y los
datos existentes (solo las renombra), y ESTADO_CUOTA se reutiliza de
creditos_ventas para que ambos planes usen los mismos estados.
"""
from django.db import models
from django.core.validators import MinValueValidator
from decimal import Decimal

from creditos_ventas.models import ESTADO_CUOTA
from purchasing.models import Purchase


class CuotaCompra(models.Model):
    """Una cuota mensual del plan de crédito de una compra a proveedor."""
    compra = models.ForeignKey(Purchase, on_delete=models.PROTECT, related_name='cuotas')
    numero = models.PositiveIntegerField()
    fecha_vencimiento = models.DateField()
    valor = models.DecimalField(max_digits=12, decimal_places=2,
                                validators=[MinValueValidator(Decimal('0.01'))])
    saldo = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    estado = models.CharField(max_length=15, choices=ESTADO_CUOTA, default='PENDIENTE')

    class Meta:
        ordering = ['compra_id', 'numero']
        constraints = [
            models.UniqueConstraint(fields=['compra', 'numero'], name='unique_cuota_compra_numero'),
        ]

    def __str__(self):
        return f'Cuota {self.numero} - Compra #{self.compra_id}'


class PagoCuotaCompra(models.Model):
    """Un abono/pago registrado contra una CuotaCompra.

    PROTECT en `cuota`: no se puede borrar una cuota que ya tiene pagos
    registrados (regla de negocio del caso de estudio)."""
    cuota = models.ForeignKey(CuotaCompra, on_delete=models.PROTECT, related_name='pagos')
    fecha = models.DateField()
    valor = models.DecimalField(max_digits=12, decimal_places=2,
                                validators=[MinValueValidator(Decimal('0.01'))])
    observacion = models.TextField(blank=True)

    class Meta:
        ordering = ['-fecha', '-id']

    def __str__(self):
        return f'Pago cuota #{self.cuota_id} - ${self.valor}'
