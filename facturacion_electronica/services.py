"""Orquestador del ciclo del comprobante electrónico (máquina de estados).

Flujo del SRI: GENERADO → FIRMADO → RECIBIDO → AUTORIZADO. Cada llamada a
``avanzar_estado`` ejecuta UNA transición (el botón "Enviar al SRI" del
detalle de la factura), registrando la respuesta simulada en ``mensajes``."""
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from .models import ComprobanteElectronico
from .xml_builder import generar_xml_factura
from .firma import firmar_xml_simulado
from .sri_simulado import enviar_recepcion, solicitar_autorizacion


def _log(comprobante, texto):
    """Agrega una línea con fecha/hora a la bitácora del comprobante."""
    sello = timezone.localtime().strftime('%d/%m/%Y %H:%M:%S')
    linea = f'[{sello}] {texto}'
    comprobante.mensajes = (comprobante.mensajes + '\n' + linea).strip() if comprobante.mensajes else linea


def generar_comprobante(invoice):
    """Crea (o devuelve) el comprobante de la factura en estado GENERADO,
    con el XML ya generado (sin firmar). Idempotente."""
    comprobante, creado = ComprobanteElectronico.objects.get_or_create(
        invoice=invoice,
        defaults={
            'ambiente': str(settings.EMPRESA['ambiente']),
            'clave_acceso': invoice.clave_acceso or '',
            'estado': ComprobanteElectronico.GENERADO,
        },
    )
    if creado:
        comprobante.xml_generado = generar_xml_factura(invoice)
        _log(comprobante, 'XML del comprobante GENERADO.')
        comprobante.save(update_fields=['xml_generado', 'mensajes'])
    return comprobante


@transaction.atomic
def avanzar_estado(comprobante):
    """Ejecuta la siguiente transición del ciclo. Devuelve el comprobante.
    No hace nada si ya está AUTORIZADO (idempotente)."""
    estado = comprobante.estado

    if estado == ComprobanteElectronico.GENERADO:
        # Firma electrónica (simulada).
        comprobante.xml_generado = firmar_xml_simulado(comprobante.xml_generado)
        comprobante.estado = ComprobanteElectronico.FIRMADO
        _log(comprobante, 'Comprobante FIRMADO electrónicamente (XAdES-BES simulado).')
        comprobante.save(update_fields=['xml_generado', 'estado', 'mensajes', 'updated_at'])

    elif estado == ComprobanteElectronico.FIRMADO:
        # Envío al servicio de recepción del SRI (simulado).
        resp = enviar_recepcion(comprobante)
        if resp['estado'] == 'RECIBIDA':
            comprobante.estado = ComprobanteElectronico.RECIBIDO
        else:
            comprobante.estado = ComprobanteElectronico.DEVUELTO
        _log(comprobante, f"Recepción SRI: {resp['estado']}. {resp['mensaje']}")
        comprobante.save(update_fields=['estado', 'mensajes', 'updated_at'])

    elif estado == ComprobanteElectronico.RECIBIDO:
        # Solicitud de autorización al SRI (simulado).
        resp = solicitar_autorizacion(comprobante)
        comprobante.estado = ComprobanteElectronico.AUTORIZADO
        comprobante.numero_autorizacion = resp['numeroAutorizacion']
        comprobante.fecha_autorizacion = resp['fechaAutorizacion']
        comprobante.xml_autorizado = resp['xml_autorizado']
        _log(comprobante, f"Autorización SRI: AUTORIZADO. N.º {resp['numeroAutorizacion']}.")
        comprobante.save(update_fields=['estado', 'numero_autorizacion', 'fecha_autorizacion',
                                        'xml_autorizado', 'mensajes', 'updated_at'])

    # AUTORIZADO o DEVUELTO: no avanza más (idempotente).
    return comprobante


def procesar_todo(comprobante):
    """Corre todas las transiciones hasta AUTORIZADO (útil en tests o para un
    procesado de una sola vez). El flujo interactivo usa avanzar_estado."""
    seguro = 0
    while comprobante.estado not in (ComprobanteElectronico.AUTORIZADO,
                                     ComprobanteElectronico.DEVUELTO) and seguro < 10:
        avanzar_estado(comprobante)
        seguro += 1
    return comprobante
