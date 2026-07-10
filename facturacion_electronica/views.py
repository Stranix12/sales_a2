from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.utils import timezone

from billing.models import Invoice
from .ride import ride_pdf_response
from .services import generar_comprobante, avanzar_estado


def xml_response(invoice):
    """Descarga del XML: el autorizado si existe, si no el firmado/generado."""
    comprobante = getattr(invoice, 'comprobante', None)
    xml = ''
    if comprobante:
        xml = comprobante.xml_autorizado or comprobante.xml_generado
    stamp = timezone.localtime().strftime('%Y%m%d_%H%M')
    num = (invoice.numero_factura or f'ID{invoice.id}').replace('-', '')
    response = HttpResponse(xml, content_type='application/xml; charset=utf-8')
    response['Content-Disposition'] = f'attachment; filename="Factura_{num}_{stamp}.xml"'
    return response


# ============================================================ staff =====
@login_required
@permission_required('facturacion_electronica.change_comprobanteelectronico', raise_exception=True)
def enviar_al_sri(request, invoice_id):
    """Avanza el comprobante una etapa del ciclo del SRI (Generado → Firmado
    → Recibido → Autorizado). Crea el comprobante si aún no existe."""
    invoice = get_object_or_404(Invoice, pk=invoice_id)
    if request.method != 'POST':
        return redirect('billing:invoice_detail', pk=invoice_id)

    comprobante = generar_comprobante(invoice)
    if comprobante.siguiente_estado is None:
        messages.info(request, f'El comprobante ya está {comprobante.get_estado_display().upper()}.')
    else:
        avanzar_estado(comprobante)
        comprobante.refresh_from_db()
        messages.success(request, f'Comprobante enviado al SRI: ahora está {comprobante.get_estado_display().upper()}.')
    return redirect('billing:invoice_detail', pk=invoice_id)


@login_required
@permission_required('facturacion_electronica.view_comprobanteelectronico', raise_exception=True)
def descargar_xml(request, invoice_id):
    invoice = get_object_or_404(Invoice, pk=invoice_id)
    return xml_response(invoice)


@login_required
@permission_required('facturacion_electronica.view_comprobanteelectronico', raise_exception=True)
def descargar_ride(request, invoice_id):
    invoice = get_object_or_404(Invoice, pk=invoice_id)
    return ride_pdf_response(invoice)
