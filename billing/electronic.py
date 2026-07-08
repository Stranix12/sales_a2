"""Facturación electrónica *simulada* (sin conexión real al SRI).

Genera los dos identificadores que dan realismo a una factura electrónica
ecuatoriana, calculados localmente a partir de los datos del emisor
(``settings.EMPRESA``) y de la propia factura:

- ``numero_factura``: secuencial con formato ``001-001-000000001``
  (establecimiento - punto de emisión - secuencial de 9 dígitos).
- ``clave_acceso``: cadena de 49 dígitos con la estructura del SRI
  (fecha + tipo + RUC + ambiente + serie + secuencial + código + tipo de
  emisión + dígito verificador módulo 11).

No hay ninguna llamada de red: es un ejercicio académico, no una integración.
"""
from django.conf import settings
from django.utils import timezone


def generar_numero_factura(invoice):
    """001-001-<secuencial de 9 dígitos>, usando el id de la factura."""
    emp = settings.EMPRESA
    return f"{emp['establecimiento']}-{emp['punto_emision']}-{invoice.pk:09d}"


def _digito_verificador_mod11(cadena48):
    """Dígito verificador módulo 11 sobre los 48 dígitos previos (algoritmo SRI)."""
    pesos = [2, 3, 4, 5, 6, 7]
    total = 0
    for i, ch in enumerate(reversed(cadena48)):
        total += int(ch) * pesos[i % len(pesos)]
    resto = total % 11
    dv = 11 - resto
    if dv == 11:
        dv = 0
    elif dv == 10:
        dv = 1
    return str(dv)


def generar_clave_acceso(invoice):
    """Clave de acceso de 49 dígitos (estructura SRI), calculada localmente."""
    emp = settings.EMPRESA
    fecha = timezone.localtime(invoice.invoice_date) if invoice.invoice_date else timezone.localtime()
    fecha_emision = fecha.strftime('%d%m%Y')          # 8
    tipo_comprobante = '01'                            # 2  (01 = factura)
    ruc = emp['ruc'].zfill(13)[:13]                    # 13
    ambiente = str(emp['ambiente'])[:1]               # 1
    serie = f"{emp['establecimiento']}{emp['punto_emision']}"  # 6 (001 + 001)
    secuencial = f'{invoice.pk:09d}'                   # 9
    codigo_numerico = f'{invoice.pk:08d}'[:8]          # 8
    tipo_emision = '1'                                 # 1 (normal)
    base48 = (fecha_emision + tipo_comprobante + ruc + ambiente
              + serie + secuencial + codigo_numerico + tipo_emision)
    return base48 + _digito_verificador_mod11(base48)


def asignar_datos_electronicos(invoice):
    """Rellena numero_factura y clave_acceso si aún no los tiene, y guarda.
    Se llama tras crear la factura (cuando ya tiene pk)."""
    changed = False
    if not invoice.numero_factura:
        invoice.numero_factura = generar_numero_factura(invoice)
        changed = True
    if not invoice.clave_acceso:
        invoice.clave_acceso = generar_clave_acceso(invoice)
        changed = True
    if changed:
        invoice.save(update_fields=['numero_factura', 'clave_acceso'])
    return invoice
