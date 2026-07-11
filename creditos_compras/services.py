"""Lógica de negocio del crédito de compras.

El algoritmo (generar cuotas mensuales, registrar pagos con validaciones y
sincronizar saldo/estado del documento) es el mismo que el del crédito de
ventas, así que se reutiliza la implementación parametrizada de
creditos_ventas.services (_generar_cuotas/_registrar_pagos) aplicada a los
modelos de esta app (Purchase + CuotaCompra + PagoCuotaCompra).
"""
from creditos_ventas.services import _generar_cuotas, _registrar_pagos

from .models import CuotaCompra, PagoCuotaCompra


def generar_cuotas_compra(purchase, num_cuotas):
    """Genera el plan de cuotas mensuales de una compra a crédito."""
    return _generar_cuotas(purchase, num_cuotas, cuota_model=CuotaCompra, doc_attr='compra')


def registrar_pagos_compra(cuotas_con_montos, fecha, observacion='', user=None):
    """Registra abonos contra una o varias cuotas de compra (todo o nada)."""
    return _registrar_pagos(cuotas_con_montos, fecha, observacion,
                            pago_model=PagoCuotaCompra, doc_attr='compra', user=user)
