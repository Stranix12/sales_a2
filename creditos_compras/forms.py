"""Formularios del crédito de compras.

Los formularios son idénticos a los del crédito de ventas (elegir tipo de
pago al registrar el documento, registrar pagos de cuotas, filtrar el
listado), así que se reutilizan los de creditos_ventas.forms; este módulo
los re-exporta para que purchasing y las vistas de esta app dependan de
creditos_compras y no de la app de ventas.
"""
from creditos_ventas.forms import (  # noqa: F401
    TIPO_PAGO_CHOICES,
    tipo_pago_field,
    num_cuotas_field,
    validar_tipo_pago,
    RegistrarPagoForm,
    CuotaPagoRowForm,
    CuotaPagoFormSet,
    CuotaFilterForm,
)
