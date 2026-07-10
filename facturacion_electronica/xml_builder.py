"""Generación del XML de una factura según la estructura del SRI de Ecuador
(esquema *factura* v1.1.0). Simulación académica: se arma un XML fiel a la
forma real, sin conexión ni validación contra los XSD oficiales.

Usa ``lxml`` (ya en requirements) y reutiliza los identificadores que ya
calcula ``billing.electronic`` (clave de acceso, número de factura)."""
from decimal import Decimal, ROUND_HALF_UP

from django.conf import settings
from django.utils import timezone

from lxml import etree

# Código del SRI para el IVA 15% (codigoPorcentaje 4). El proyecto factura
# siempre con IVA 15%, así que se fija aquí.
IVA_CODIGO = '2'            # 2 = IVA
IVA_COD_PORCENTAJE = '4'    # 4 = 15%
IVA_TARIFA = '15.00'


def _dec(valor):
    """Formatea un número con exactamente 2 decimales (formato SRI)."""
    return str(Decimal(valor or 0).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP))


def _tipo_identificacion(dni):
    """Deriva el tipo de identificación del comprador a partir del DNI/RUC:
    04=RUC (13 díg.), 05=Cédula (10 díg.), 06=Pasaporte/otros."""
    dni = (dni or '').strip()
    if len(dni) == 13:
        return '04'
    if len(dni) == 10:
        return '05'
    return '06'


def _secuencial(invoice):
    """Los 9 dígitos finales del número de factura (001-001-000000001)."""
    numero = invoice.numero_factura or ''
    if '-' in numero:
        return numero.split('-')[-1]
    return f'{invoice.pk:09d}'


def generar_xml_factura(invoice):
    """Devuelve el XML (str) de la factura con la estructura del SRI."""
    emp = settings.EMPRESA
    cust = invoice.customer
    fecha = timezone.localtime(invoice.invoice_date) if invoice.invoice_date else timezone.localtime()

    factura = etree.Element('factura', id='comprobante', version='1.1.0')

    # --- infoTributaria ---
    it = etree.SubElement(factura, 'infoTributaria')
    etree.SubElement(it, 'ambiente').text = str(emp['ambiente'])
    etree.SubElement(it, 'tipoEmision').text = '1'
    etree.SubElement(it, 'razonSocial').text = emp['nombre']
    etree.SubElement(it, 'nombreComercial').text = emp.get('nombre_comercial', emp['nombre'])
    etree.SubElement(it, 'ruc').text = emp['ruc']
    etree.SubElement(it, 'claveAcceso').text = invoice.clave_acceso or ''
    etree.SubElement(it, 'codDoc').text = '01'  # 01 = factura
    etree.SubElement(it, 'estab').text = emp['establecimiento']
    etree.SubElement(it, 'ptoEmi').text = emp['punto_emision']
    etree.SubElement(it, 'secuencial').text = _secuencial(invoice)
    etree.SubElement(it, 'dirMatriz').text = emp['direccion']

    # --- infoFactura ---
    inf = etree.SubElement(factura, 'infoFactura')
    etree.SubElement(inf, 'fechaEmision').text = fecha.strftime('%d/%m/%Y')
    etree.SubElement(inf, 'dirEstablecimiento').text = emp['direccion']
    etree.SubElement(inf, 'obligadoContabilidad').text = emp.get('obligado_contabilidad', 'NO')
    etree.SubElement(inf, 'tipoIdentificacionComprador').text = _tipo_identificacion(cust.dni)
    etree.SubElement(inf, 'razonSocialComprador').text = cust.full_name
    etree.SubElement(inf, 'identificacionComprador').text = cust.dni
    etree.SubElement(inf, 'direccionComprador').text = cust.address or 'S/N'
    etree.SubElement(inf, 'totalSinImpuestos').text = _dec(invoice.subtotal)
    etree.SubElement(inf, 'totalDescuento').text = '0.00'

    tci = etree.SubElement(inf, 'totalConImpuestos')
    ti = etree.SubElement(tci, 'totalImpuesto')
    etree.SubElement(ti, 'codigo').text = IVA_CODIGO
    etree.SubElement(ti, 'codigoPorcentaje').text = IVA_COD_PORCENTAJE
    etree.SubElement(ti, 'baseImponible').text = _dec(invoice.subtotal)
    etree.SubElement(ti, 'valor').text = _dec(invoice.tax)

    etree.SubElement(inf, 'propina').text = '0.00'
    etree.SubElement(inf, 'importeTotal').text = _dec(invoice.total)
    etree.SubElement(inf, 'moneda').text = 'DOLAR'

    # pagos: contado -> 01 (sin sistema financiero); crédito -> 20 con plazo
    pagos = etree.SubElement(inf, 'pagos')
    pago = etree.SubElement(pagos, 'pago')
    if invoice.tipo_pago == 'CREDITO':
        n_cuotas = invoice.cuotas.count()
        etree.SubElement(pago, 'formaPago').text = '20'  # otros / sistema financiero
        etree.SubElement(pago, 'total').text = _dec(invoice.total)
        etree.SubElement(pago, 'plazo').text = str(n_cuotas)
        etree.SubElement(pago, 'unidadTiempo').text = 'meses'
    else:
        etree.SubElement(pago, 'formaPago').text = '01'  # sin utilización sistema financiero
        etree.SubElement(pago, 'total').text = _dec(invoice.total)

    # --- detalles ---
    detalles = etree.SubElement(factura, 'detalles')
    for d in invoice.details.select_related('product'):
        det = etree.SubElement(detalles, 'detalle')
        etree.SubElement(det, 'codigoPrincipal').text = f'P{d.product_id}'
        etree.SubElement(det, 'descripcion').text = d.product.name
        etree.SubElement(det, 'cantidad').text = _dec(d.quantity)
        etree.SubElement(det, 'precioUnitario').text = _dec(d.unit_price)
        etree.SubElement(det, 'descuento').text = '0.00'
        etree.SubElement(det, 'precioTotalSinImpuesto').text = _dec(d.subtotal)
        imps = etree.SubElement(det, 'impuestos')
        imp = etree.SubElement(imps, 'impuesto')
        etree.SubElement(imp, 'codigo').text = IVA_CODIGO
        etree.SubElement(imp, 'codigoPorcentaje').text = IVA_COD_PORCENTAJE
        etree.SubElement(imp, 'tarifa').text = IVA_TARIFA
        etree.SubElement(imp, 'baseImponible').text = _dec(d.subtotal)
        iva_linea = (Decimal(d.subtotal) * Decimal('0.15')).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        etree.SubElement(imp, 'valor').text = _dec(iva_linea)

    # --- infoAdicional ---
    extra = etree.SubElement(factura, 'infoAdicional')
    if cust.email:
        etree.SubElement(extra, 'campoAdicional', nombre='Email').text = cust.email
    if cust.phone:
        etree.SubElement(extra, 'campoAdicional', nombre='Teléfono').text = cust.phone
    etree.SubElement(extra, 'campoAdicional', nombre='Tipo de pago').text = invoice.get_tipo_pago_display()

    return etree.tostring(factura, pretty_print=True, xml_declaration=True,
                          encoding='UTF-8').decode('utf-8')
