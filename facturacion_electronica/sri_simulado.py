"""Simulación de los web services del SRI: recepción y autorización.

El SRI real expone dos servicios SOAP: uno de *recepción* (recibe el XML
firmado y responde RECIBIDA/DEVUELTA) y otro de *autorización* (responde
AUTORIZADO/NO AUTORIZADO con el número y fecha de autorización). Aquí se
imitan ambas respuestas **sin red**, con validaciones básicas, para el
ejercicio académico."""
from lxml import etree

from django.utils import timezone


def enviar_recepcion(comprobante):
    """Simula el servicio de recepción del SRI. Devuelve un dict con
    'estado' ('RECIBIDA'/'DEVUELTA') y 'mensaje'."""
    errores = []
    if not comprobante.clave_acceso or len(comprobante.clave_acceso) != 49:
        errores.append('Clave de acceso inválida (debe tener 49 dígitos).')
    if not comprobante.xml_generado:
        errores.append('No hay XML firmado que enviar.')

    if errores:
        return {'estado': 'DEVUELTA', 'mensaje': ' '.join(errores)}
    return {'estado': 'RECIBIDA',
            'mensaje': 'Comprobante recibido por el SRI (simulado). En proceso de autorización.'}


def solicitar_autorizacion(comprobante):
    """Simula el servicio de autorización del SRI. Devuelve un dict con
    'estado' ('AUTORIZADO'/'NO AUTORIZADO'), 'numeroAutorizacion',
    'fechaAutorizacion' y el 'xml_autorizado' (XML de respuesta que envuelve
    al comprobante, tal como lo entrega el SRI real)."""
    ahora = timezone.now()
    # Desde 2014 el número de autorización del SRI ES la clave de acceso.
    numero_autorizacion = comprobante.clave_acceso

    aut = etree.Element('autorizacion')
    etree.SubElement(aut, 'estado').text = 'AUTORIZADO'
    etree.SubElement(aut, 'numeroAutorizacion').text = numero_autorizacion
    etree.SubElement(aut, 'fechaAutorizacion').text = timezone.localtime(ahora).strftime('%Y-%m-%dT%H:%M:%S')
    etree.SubElement(aut, 'ambiente').text = comprobante.ambiente_display
    # El comprobante firmado va como CDATA dentro de la respuesta (formato SRI).
    comp = etree.SubElement(aut, 'comprobante')
    comp.text = etree.CDATA(comprobante.xml_generado)
    mensajes = etree.SubElement(aut, 'mensajes')  # vacío = sin observaciones
    mensajes.text = ''

    xml_autorizado = etree.tostring(aut, pretty_print=True, xml_declaration=True,
                                    encoding='UTF-8').decode('utf-8')

    return {
        'estado': 'AUTORIZADO',
        'numeroAutorizacion': numero_autorizacion,
        'fechaAutorizacion': ahora,
        'xml_autorizado': xml_autorizado,
        'mensaje': 'Comprobante AUTORIZADO por el SRI (simulado).',
    }
