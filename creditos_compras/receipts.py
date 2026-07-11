"""Comprobante de pago de una cuota de compra — un PDF imprimible por cada
abono registrado. El diseño (cabecera con la marca, información del crédito,
detalle de la cuota pagada y estado del crédito con barra de progreso) es el
mismo del crédito de ventas, así que se reutiliza el constructor compartido
de creditos_ventas.receipts aplicado a la compra y su proveedor."""
from django.utils import timezone

from creditos_ventas.receipts import _build_receipt_pdf, _fecha, _money, _response, _resumen_credito


def build_pago_cuota_compra_pdf_bytes(pago):
    cuota = pago.cuota
    purchase = cuota.compra
    supplier = purchase.supplier
    cuotas = list(purchase.cuotas.all())
    total_credito, restantes, proxima = _resumen_credito(cuotas, purchase.saldo)
    return _build_receipt_pdf(
        numero_comprobante=f'CP-{pago.pk:06d}',
        contraparte_titulo='DATOS DEL PROVEEDOR',
        contraparte_rows=[
            ('Proveedor', str(supplier)),
            ('Correo', getattr(supplier, 'email', None) or '—'),
            ('Teléfono', getattr(supplier, 'phone', None) or '—'),
        ],
        credito_rows=[
            ('N.º de compra', f'#{purchase.pk}'),
            ('Documento', purchase.document_number or '—'),
            ('Fecha', _fecha(purchase.purchase_date)),
            ('Forma de pago', f'Crédito a {len(cuotas)} meses'),
            ('Total del documento', _money(purchase.total)),
        ],
        pago=pago, cuota=cuota, total_cuotas=len(cuotas), total_credito=total_credito,
        saldo_documento=purchase.saldo, cuotas_restantes=restantes, proxima_cuota=proxima,
    )


def pago_cuota_compra_pdf_response(pago):
    stamp = timezone.localtime().strftime('%Y%m%d_%H%M')
    filename = f'Recibo_Compra{pago.cuota.compra_id}_Cuota{pago.cuota.numero}_{stamp}.pdf'
    return _response(build_pago_cuota_compra_pdf_bytes(pago), filename)
