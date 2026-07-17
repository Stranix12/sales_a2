from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.utils import timezone

from billing.models import Invoice
from shared.emails import send_invoice_email
from .models import ComprobanteElectronico
from .ride import ride_pdf_response
from .services import procesar_completo


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
@permission_required('facturacion_electronica.send_comprobanteelectronico', raise_exception=True)
def enviar_al_sri(request, invoice_id):
    """Corre el ciclo completo del SRI de una sola vez (Generado → Firmado →
    Recibido → Autorizado). Crea el comprobante si aún no existe. La
    animación paso a paso que ve quien hace clic es del lado del cliente
    (ver invoice_detail.html); acá el servidor ya termina todo en una sola
    llamada, como un trámite real."""
    invoice = get_object_or_404(Invoice, pk=invoice_id)
    if request.method != 'POST':
        return redirect('billing:invoice_detail', pk=invoice_id)

    # Consulta directa (no invoice.comprobante): acceder a la relación
    # inversa ANTES de que exista el comprobante deja en caché "no existe"
    # sobre este mismo objeto invoice, y ese caché no se invalida después --
    # send_invoice_email() más abajo volvería a leer ese caché viejo y
    # nunca adjuntaría el XML recién autorizado.
    ya_autorizado = ComprobanteElectronico.objects.filter(
        invoice=invoice, estado=ComprobanteElectronico.AUTORIZADO,
    ).exists()

    comprobante = procesar_completo(invoice)

    if ya_autorizado:
        messages.info(request, f'El comprobante ya está {comprobante.get_estado_display().upper()}.')
    elif comprobante.estado == ComprobanteElectronico.AUTORIZADO:
        messages.success(
            request,
            f'Comprobante AUTORIZADO por el SRI. N.º de autorización: {comprobante.numero_autorizacion}.',
        )
        # Recién autorizado: reenvía la factura al cliente con el RIDE final
        # y el XML autorizado adjuntos (fuera de cualquier transacción, como
        # el resto de los envíos de correo del proyecto).
        if send_invoice_email(invoice):
            messages.info(request, 'Se reenvió la factura al cliente con el XML autorizado adjunto.')
    elif comprobante.estado == ComprobanteElectronico.DEVUELTO:
        messages.error(
            request,
            'El SRI devolvió el comprobante. Revisa los datos de la factura e inténtalo de nuevo.',
        )
    else:
        messages.info(request, f'El comprobante quedó en {comprobante.get_estado_display().upper()}.')
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
