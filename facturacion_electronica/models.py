from django.db import models

from billing.models import Invoice


class ComprobanteElectronico(models.Model):
    """Comprobante electrónico *simulado* de una factura, siguiendo el ciclo
    del SRI de Ecuador: se genera el XML, se firma (simulado), se envía a
    recepción y se solicita la autorización. Cada paso avanza el `estado`.

    El XML se guarda en la base (TextField), no como archivo, para que
    persista en Render sin depender de almacenamiento de MEDIA."""

    # Orden del ciclo del SRI. La máquina de estados de services.py solo
    # permite avanzar al siguiente (no saltar pasos).
    GENERADO = 'GENERADO'
    FIRMADO = 'FIRMADO'
    RECIBIDO = 'RECIBIDO'
    AUTORIZADO = 'AUTORIZADO'
    DEVUELTO = 'DEVUELTO'
    ESTADOS = [
        (GENERADO, 'Generado'),
        (FIRMADO, 'Firmado'),
        (RECIBIDO, 'Recibido'),
        (AUTORIZADO, 'Autorizado'),
        (DEVUELTO, 'Devuelto'),
    ]
    # Secuencia feliz del ciclo (para avanzar_estado en services.py).
    FLUJO = [GENERADO, FIRMADO, RECIBIDO, AUTORIZADO]

    invoice = models.OneToOneField(Invoice, on_delete=models.CASCADE, related_name='comprobante')
    estado = models.CharField(max_length=12, choices=ESTADOS, default=GENERADO)
    ambiente = models.CharField(max_length=1, default='1', help_text='1=Pruebas, 2=Producción')
    clave_acceso = models.CharField(max_length=49, blank=True)
    numero_autorizacion = models.CharField(max_length=49, blank=True)
    fecha_autorizacion = models.DateTimeField(null=True, blank=True)
    xml_generado = models.TextField(blank=True, help_text='XML firmado (simulado)')
    xml_autorizado = models.TextField(blank=True, help_text='XML dentro de la respuesta de autorización')
    mensajes = models.TextField(blank=True, help_text='Bitácora de las respuestas simuladas del SRI')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Comprobante electrónico'
        verbose_name_plural = 'Comprobantes electrónicos'
        ordering = ['-created_at']
        permissions = [
            ('send_comprobanteelectronico', 'Puede enviar comprobantes al SRI'),
        ]

    def __str__(self):
        return f'Comprobante {self.clave_acceso or self.invoice_id} ({self.estado})'

    @property
    def ambiente_display(self):
        return 'PRODUCCIÓN' if self.ambiente == '2' else 'PRUEBAS'

    @property
    def esta_autorizado(self):
        return self.estado == self.AUTORIZADO

    @property
    def siguiente_estado(self):
        """El estado al que avanzaría 'Enviar al SRI', o None si ya terminó."""
        if self.estado in self.FLUJO and self.estado != self.AUTORIZADO:
            return self.FLUJO[self.FLUJO.index(self.estado) + 1]
        return None
