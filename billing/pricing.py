"""Cálculo de subtotal/IVA a partir de líneas de factura o carrito.

El IVA es por línea, no global: los productos con ``iva_tarifa_0=True`` (ej.
alimentos básicos, medicinas) no generan IVA; el resto factura con la
tarifa general (15%). Una misma factura puede combinar ambos.

Una sola fuente de verdad para este cálculo: lo usan tanto la creación de
factura desde el panel interno (views.py) como el carrito y el checkout del
portal del cliente (portal_views.py), para que ambos caminos calculen
exactamente lo mismo."""
from decimal import Decimal, ROUND_HALF_UP

IVA_TARIFA_GENERAL = Decimal('0.15')


def calcular_subtotal_iva(pares_producto_subtotal):
    """`pares_producto_subtotal`: iterable de (product, subtotal_de_la_linea).
    Devuelve (subtotal, iva) como Decimal."""
    subtotal = Decimal('0')
    iva = Decimal('0')
    for product, monto in pares_producto_subtotal:
        subtotal += monto
        if not product.iva_tarifa_0:
            iva += (monto * IVA_TARIFA_GENERAL).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    return subtotal, iva


def desglose_iva_por_tarifa(pares_producto_subtotal):
    """Como calcular_subtotal_iva, pero desglosado por tarifa: el SRI exige
    declarar la base imponible de cada tarifa por separado (Formulario 104),
    no solo el IVA total. Usado por el reporte de IVA (billing/reports.py).
    Devuelve un dict de Decimal: base_15, iva_15, base_0 (siempre exenta de
    IVA, por eso no hay iva_0), total_base, total_iva, total."""
    base_15 = Decimal('0')
    iva_15 = Decimal('0')
    base_0 = Decimal('0')
    for product, monto in pares_producto_subtotal:
        if product.iva_tarifa_0:
            base_0 += monto
        else:
            base_15 += monto
            iva_15 += (monto * IVA_TARIFA_GENERAL).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    return {
        'base_15': base_15, 'iva_15': iva_15, 'base_0': base_0,
        'total_base': base_15 + base_0, 'total_iva': iva_15,
        'total': base_15 + base_0 + iva_15,
    }
