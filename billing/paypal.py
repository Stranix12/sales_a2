"""Integración con PayPal (Orders API v2) en modo Sandbox por defecto.

Se usa la REST API directamente con ``requests`` (no ``paypalrestsdk``, que
PayPal considera legacy) con dos llamadas por operación: OAuth2 client
credentials para el token, y create/capture order. Cambiar a producción real
es solo cuestión de variables de entorno (``PAYPAL_MODE=live`` + credenciales
Live) — el código de este módulo no cambia.

Flujo:
  1. ``create_order(invoice, request)`` -> crea la orden en PayPal y devuelve
     el link de aprobación al que se redirige al usuario.
  2. El usuario aprueba el pago en PayPal (con una cuenta de prueba Sandbox).
  3. PayPal redirige de vuelta a ``return_url`` con ``?token=<order_id>``.
  4. ``capture_order(order_id)`` -> cobra la orden aprobada.
"""
import logging

import requests
from django.conf import settings
from django.urls import reverse

logger = logging.getLogger('paypal')

_BASE_URLS = {
    'sandbox': 'https://api-m.sandbox.paypal.com',
    'live': 'https://api-m.paypal.com',
}


class PayPalError(Exception):
    """Error de comunicación o de respuesta inesperada de PayPal."""


def is_configured():
    return bool(settings.PAYPAL_CLIENT_ID and settings.PAYPAL_CLIENT_SECRET)


def _base_url():
    return _BASE_URLS.get(settings.PAYPAL_MODE, _BASE_URLS['sandbox'])


def _get_access_token():
    if not is_configured():
        raise PayPalError('PayPal no está configurado (faltan PAYPAL_CLIENT_ID/SECRET).')
    try:
        resp = requests.post(
            f'{_base_url()}/v1/oauth2/token',
            auth=(settings.PAYPAL_CLIENT_ID, settings.PAYPAL_CLIENT_SECRET),
            data={'grant_type': 'client_credentials'},
            timeout=10,
        )
        resp.raise_for_status()
    except requests.RequestException as exc:
        logger.exception('Fallo obteniendo token de PayPal')
        raise PayPalError('No se pudo conectar con PayPal.') from exc
    return resp.json()['access_token']


def create_order(invoice, request,
                 return_urlname='billing:invoice_paypal_return',
                 cancel_urlname='billing:invoice_paypal_cancel'):
    """Crea la orden por el total de la factura. Devuelve (order_id, approve_url).

    Los nombres de URL de retorno/cancelación son parametrizables porque el
    flujo se usa desde dos lugares: la vista interna (vendedor/admin) y el
    portal del cliente, cada uno con sus propias rutas."""
    token = _get_access_token()
    return_url = request.build_absolute_uri(
        reverse(return_urlname, args=[invoice.pk]))
    cancel_url = request.build_absolute_uri(
        reverse(cancel_urlname, args=[invoice.pk]))
    payload = {
        'intent': 'CAPTURE',
        'purchase_units': [{
            'reference_id': invoice.numero_factura or str(invoice.pk),
            'description': f'Factura {invoice.numero_factura or invoice.pk} - {settings.EMPRESA["nombre"]}',
            'amount': {'currency_code': 'USD', 'value': f'{invoice.total:.2f}'},
        }],
        'application_context': {
            'return_url': return_url,
            'cancel_url': cancel_url,
            'brand_name': settings.EMPRESA['nombre'],
            'user_action': 'PAY_NOW',
        },
    }
    try:
        resp = requests.post(
            f'{_base_url()}/v2/checkout/orders',
            json=payload,
            headers={'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'},
            timeout=10,
        )
        resp.raise_for_status()
    except requests.RequestException as exc:
        logger.exception('Fallo creando orden PayPal para factura #%s', invoice.pk)
        raise PayPalError('No se pudo crear la orden de pago en PayPal.') from exc

    data = resp.json()
    approve_url = next((l['href'] for l in data.get('links', []) if l.get('rel') == 'approve'), None)
    if not approve_url:
        raise PayPalError('PayPal no devolvió un link de aprobación.')
    return data['id'], approve_url


def capture_order(order_id):
    """Captura (cobra) una orden ya aprobada. Devuelve (status, capture_id)."""
    token = _get_access_token()
    try:
        resp = requests.post(
            f'{_base_url()}/v2/checkout/orders/{order_id}/capture',
            headers={'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'},
            timeout=10,
        )
        resp.raise_for_status()
    except requests.RequestException as exc:
        logger.exception('Fallo capturando orden PayPal %s', order_id)
        raise PayPalError('No se pudo confirmar el pago con PayPal.') from exc

    data = resp.json()
    status = data.get('status')
    capture_id = None
    try:
        capture_id = data['purchase_units'][0]['payments']['captures'][0]['id']
    except (KeyError, IndexError):
        pass
    return status, capture_id
