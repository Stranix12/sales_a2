"""Envío de correos transaccionales (bienvenida, factura creada).

El backend se configura en settings.EMAIL_BACKEND: consola en desarrollo
(los correos se imprimen en la terminal de runserver), SMTP real en
producción. Las funciones nunca lanzan excepción hacia la vista que las
llama: si el envío falla (o el destinatario no tiene email), se registra
en el logger 'emails' y se retorna False, para no romper el flujo de
registro/facturación por un problema de correo.
"""
import logging

from django.conf import settings
from django.core.mail import send_mail, EmailMessage
from django.template.loader import render_to_string

logger = logging.getLogger('emails')


def send_welcome_email(user, temp_password=None, login_url=None):
    """Correo de bienvenida al crear un usuario.

    Si `temp_password` viene con valor (la contraseña que el Administrador
    le asignó, automática o manual), se incluye en el correo junto con el
    aviso de que el sistema la va a obligar a cambiarla en su primer login.
    `login_url` es la URL absoluta de login (la arma la vista con
    request.build_absolute_uri, porque desde aquí no hay request); al
    entrar ahí, ForcePasswordChangeMiddleware ya lo manda solo a cambiarla.
    """
    if not user.email:
        logger.warning('Usuario "%s" sin email: no se envía correo de bienvenida.', user.username)
        return False

    roles = ', '.join(g.name for g in user.groups.all()) or 'Sin rol asignado'
    body = render_to_string('emails/user_welcome.txt', {
        'user': user, 'roles': roles, 'temp_password': temp_password, 'login_url': login_url,
    })
    try:
        send_mail(
            subject='Bienvenido a Sales System',
            message=body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
        )
        return True
    except Exception:
        logger.exception('No se pudo enviar el correo de bienvenida a %s', user.email)
        return False


def send_invoice_email(invoice):
    """Correo con el detalle de la factura + el PDF adjunto, al cliente."""
    customer = invoice.customer
    if not customer.email:
        logger.warning('Cliente "%s" sin email: no se envía la factura #%s.', customer, invoice.id)
        return False

    body = render_to_string('emails/invoice_created.txt', {
        'invoice': invoice,
        'customer': customer,
        'details': invoice.details.select_related('product'),
    })
    numero = invoice.numero_factura or f'#{invoice.id}'
    try:
        msg = EmailMessage(
            subject=f'Factura {numero} - Sales System',
            body=body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[customer.email],
        )
        # Adjuntar el PDF del comprobante. El import es local para no crear un
        # ciclo (billing.invoice_export importa modelos) ni cargar reportlab
        # cuando no hace falta.
        try:
            from billing.invoice_export import build_invoice_pdf_bytes
            pdf = build_invoice_pdf_bytes(invoice)
            msg.attach(f'Factura_{numero}.pdf'.replace('-', ''), pdf, 'application/pdf')
        except Exception:
            logger.exception('No se pudo adjuntar el PDF de la factura #%s (se envía sin adjunto).', invoice.id)
        # Adjuntar también el XML autorizado del comprobante electrónico, si ya
        # está autorizado (el SRI real entrega XML + RIDE al comprador).
        try:
            comprobante = getattr(invoice, 'comprobante', None)
            if comprobante and comprobante.xml_autorizado:
                msg.attach(f'Factura_{numero}.xml'.replace('-', ''),
                           comprobante.xml_autorizado.encode('utf-8'), 'application/xml')
        except Exception:
            logger.exception('No se pudo adjuntar el XML de la factura #%s.', invoice.id)
        msg.send()
        return True
    except Exception:
        logger.exception('No se pudo enviar la factura #%s a %s', invoice.id, customer.email)
        return False
