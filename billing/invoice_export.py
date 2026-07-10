"""PDF de una factura (RIDE del comprobante electrónico).

El PDF de la factura ES el RIDE (Representación Impresa del Documento
Electrónico) que arma ``facturacion_electronica.ride``: comprobante con
aspecto de factura autorizada por el SRI (banda de marca, código de barras de
la clave de acceso, datos de autorización, detalle, totales y plan de cuotas).
Este módulo es solo el adaptador que usan las vistas y el correo, para no
tener que cambiar sus imports.

Expone:
  - ``build_invoice_pdf_bytes(invoice)`` -> bytes  (para adjuntar al correo)
  - ``invoice_pdf_response(invoice)``    -> HttpResponse (descarga)
"""
from django.http import HttpResponse
from django.utils import timezone


def build_invoice_pdf_bytes(invoice):
    """Delega en el RIDE. Import local para evitar un ciclo de importación
    (facturacion_electronica importa modelos de billing)."""
    from facturacion_electronica.ride import build_ride_pdf_bytes
    return build_ride_pdf_bytes(invoice)


def _filename(invoice):
    stamp = timezone.localtime().strftime('%Y%m%d_%H%M')
    num = (invoice.numero_factura or f'ID{invoice.id}').replace('-', '')
    return f'Factura_{num}_{stamp}.pdf'


def invoice_pdf_response(invoice):
    response = HttpResponse(build_invoice_pdf_bytes(invoice), content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="{_filename(invoice)}"'
    return response
