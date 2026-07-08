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
from django.core.mail import send_mail
from django.template.loader import render_to_string

logger = logging.getLogger('emails')


def send_welcome_email(user, temp_password=None):
    """Correo de bienvenida al crear un usuario.

    Si `temp_password` viene con valor (la contraseña que el Administrador
    le asignó, automática o manual), se incluye en el correo junto con el
    aviso de que el sistema la va a obligar a cambiarla en su primer login.
    """
    if not user.email:
        logger.warning('Usuario "%s" sin email: no se envía correo de bienvenida.', user.username)
        return False

    roles = ', '.join(g.name for g in user.groups.all()) or 'Sin rol asignado'
    body = render_to_string('emails/user_welcome.txt', {
        'user': user, 'roles': roles, 'temp_password': temp_password,
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
    """Correo con el detalle de la factura, al cliente asociado."""
    customer = invoice.customer
    if not customer.email:
        logger.warning('Cliente "%s" sin email: no se envía la factura #%s.', customer, invoice.id)
        return False

    body = render_to_string('emails/invoice_created.txt', {
        'invoice': invoice,
        'customer': customer,
        'details': invoice.details.select_related('product'),
    })
    try:
        send_mail(
            subject=f'Factura #{invoice.id} - Sales System',
            message=body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[customer.email],
        )
        return True
    except Exception:
        logger.exception('No se pudo enviar la factura #%s a %s', invoice.id, customer.email)
        return False
