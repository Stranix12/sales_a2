"""RIDE — Representación Impresa del Documento Electrónico.

Es el PDF de la factura con el aspecto de un comprobante electrónico
autorizado por el SRI: banda de cabecera con la marca, recuadro de
autorización con el código de barras de la clave de acceso, cliente,
condiciones de pago (contado/crédito), detalle, totales y, si aplica, el
plan de cuotas. Reemplaza al PDF plano anterior; ``billing.invoice_export``
delega aquí."""
from decimal import Decimal, ROUND_HALF_UP
from io import BytesIO

from django.conf import settings
from django.http import HttpResponse
from django.utils import timezone

from reportlab.graphics.barcode import createBarcodeDrawing
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import HRFlowable, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

ACCENT = '33459B'
HEADER_FILL = '343A40'
LIGHT = 'EEF0FB'
_ESTADO_COLOR = {
    'AUTORIZADO': '1F9D57', 'RECIBIDO': '2A7DE1', 'FIRMADO': 'B9790F',
    'GENERADO': '6B7280', 'DEVUELTO': 'D64550',
}


def _money(valor):
    """Formatea un importe como '$0.00' (siempre 2 decimales), sin depender
    de la precisión con que venga el Decimal (un valor recién calculado en
    memoria puede traer más decimales que la columna de la BD)."""
    return f'${Decimal(valor or 0).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)}'


def _fecha(dt):
    return timezone.localtime(dt).strftime('%d/%m/%Y %H:%M') if dt else '—'


def _fecha_corta(d):
    return d.strftime('%d/%m/%Y') if d else '—'


def _barcode(clave, target_width):
    """Código de barras Code128 de la clave de acceso, escalado al ancho dado."""
    d = createBarcodeDrawing('Code128', value=clave or '0', barHeight=1.0 * cm,
                             humanReadable=False, quiet=False)
    if d.width:
        factor = target_width / d.width
        d.scale(factor, 1)
        d.width = target_width
    return d


def build_ride_pdf_bytes(invoice):
    emp = settings.EMPRESA
    cust = invoice.customer
    comprobante = getattr(invoice, 'comprobante', None)
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        topMargin=1.2 * cm, bottomMargin=1.2 * cm, leftMargin=1.5 * cm, rightMargin=1.5 * cm,
        title=f'Factura {invoice.numero_factura or invoice.id}',
    )
    usable = A4[0] - doc.leftMargin - doc.rightMargin

    styles = getSampleStyleSheet()
    normal = styles['Normal']
    small = ParagraphStyle('small', parent=normal, fontSize=8, leading=10, textColor=colors.HexColor('#5c6474'))
    white_big = ParagraphStyle('wb', parent=normal, fontName='Helvetica-Bold', fontSize=15, leading=19,
                               spaceAfter=3, textColor=colors.white)
    white_small = ParagraphStyle('ws', parent=normal, fontSize=8, leading=11, textColor=colors.white)
    white_doc = ParagraphStyle('wd', parent=normal, fontName='Helvetica-Bold', fontSize=17, leading=21,
                               spaceAfter=3, textColor=colors.white, alignment=2)
    white_right = ParagraphStyle('wr', parent=normal, fontSize=9, leading=12, textColor=colors.white, alignment=2)
    lbl = ParagraphStyle('lbl', parent=normal, fontName='Helvetica-Bold', fontSize=9)
    mono = ParagraphStyle('mono', parent=normal, fontName='Courier', fontSize=8, alignment=1)
    section_style = ParagraphStyle('sec', parent=normal, fontName='Helvetica-Bold', fontSize=10,
                                   textColor=colors.HexColor(f'#{ACCENT}'))

    def section(title):
        return [Paragraph(title.upper(), section_style),
                HRFlowable(width='100%', thickness=0.8, color=colors.HexColor(f'#{ACCENT}'),
                           spaceBefore=2, spaceAfter=6)]

    elements = []

    # ---------------- Banda de cabecera (marca + FACTURA) ----------------
    emisor = [
        Paragraph(emp['nombre'], white_big),
        Paragraph(f"RUC: {emp['ruc']}", white_small),
        Paragraph(emp['direccion'], white_small),
        Paragraph(f"Tel: {emp['telefono']} · {emp['email']}", white_small),
    ]
    factura_cab = [
        Paragraph('FACTURA', white_doc),
        Paragraph(f"N.º {invoice.numero_factura or '—'}", white_right),
        Paragraph(f"Fecha: {_fecha(invoice.invoice_date)}", white_right),
    ]
    header = Table([[emisor, factura_cab]], colWidths=[usable * 0.62, usable * 0.38])
    header.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor(f'#{ACCENT}')),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('TOPPADDING', (0, 0), (-1, -1), 10), ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
        ('LEFTPADDING', (0, 0), (-1, -1), 12), ('RIGHTPADDING', (0, 0), (-1, -1), 12),
    ]))
    elements += [header, Spacer(1, 0.35 * cm)]

    # ---------------- Recuadro de autorización SRI ----------------
    estado = comprobante.estado if comprobante else 'GENERADO'
    estado_disp = comprobante.get_estado_display().upper() if comprobante else 'NO GENERADO'
    estado_color = _ESTADO_COLOR.get(estado, '5c6474')
    num_aut = (comprobante.numero_autorizacion if comprobante and comprobante.numero_autorizacion
               else invoice.clave_acceso or '—')
    fecha_aut = _fecha(comprobante.fecha_autorizacion) if comprobante and comprobante.fecha_autorizacion else '—'
    ambiente = comprobante.ambiente_display if comprobante else ('PRODUCCIÓN' if str(emp['ambiente']) == '2' else 'PRUEBAS')

    estado_style = ParagraphStyle('est', parent=lbl, textColor=colors.HexColor(f'#{estado_color}'))
    sri_data = [
        [Paragraph('COMPROBANTE ELECTRÓNICO', ParagraphStyle('h', parent=lbl, textColor=colors.HexColor(f'#{ACCENT}'))), ''],
        [Paragraph('Estado SRI:', lbl), Paragraph(estado_disp, estado_style)],
        [Paragraph('Ambiente:', lbl), ambiente],
        [Paragraph('N.º Autorización:', lbl), Paragraph(num_aut, ParagraphStyle('m', parent=normal, fontName='Courier', fontSize=7))],
        [Paragraph('Fecha autorización:', lbl), fecha_aut],
    ]
    barcode = _barcode(invoice.clave_acceso, usable * 0.44 - 12)
    clave_block = [barcode, Spacer(1, 2), Paragraph('Clave de acceso', small),
                   Paragraph(invoice.clave_acceso or '—', mono)]
    sri_box = Table(
        [[Table(sri_data, colWidths=[3.3 * cm, usable * 0.56 - 3.3 * cm - 12],
                style=TableStyle([('FONTSIZE', (0, 0), (-1, -1), 8.5), ('SPAN', (0, 0), (1, 0)),
                                  ('BOTTOMPADDING', (0, 0), (-1, -1), 3), ('TOPPADDING', (0, 0), (-1, -1), 1)])),
          clave_block]],
        colWidths=[usable * 0.56, usable * 0.44],
    )
    sri_box.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor(f'#{LIGHT}')),
        ('BOX', (0, 0), (-1, -1), 0.6, colors.HexColor('#cdd4f3')),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('ALIGN', (1, 0), (1, 0), 'CENTER'),
        ('TOPPADDING', (0, 0), (-1, -1), 8), ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('LEFTPADDING', (0, 0), (-1, -1), 10), ('RIGHTPADDING', (0, 0), (-1, -1), 10),
    ]))
    elements += [sri_box, Spacer(1, 0.4 * cm)]

    # ---------------- Cliente ----------------
    elements += section('Cliente')
    elements += [
        Table([
            [Paragraph('Cliente:', lbl), cust.full_name, Paragraph('DNI/RUC:', lbl), cust.dni],
            [Paragraph('Dirección:', lbl), cust.address or '—', Paragraph('Email:', lbl), cust.email or '—'],
        ], colWidths=[2.4 * cm, usable / 2 - 2.4 * cm, 2.4 * cm, usable / 2 - 2.4 * cm],
            style=TableStyle([('VALIGN', (0, 0), (-1, -1), 'TOP'), ('FONTSIZE', (0, 0), (-1, -1), 9),
                              ('BOTTOMPADDING', (0, 0), (-1, -1), 4)])),
        Spacer(1, 0.4 * cm),
    ]

    # ---------------- Condiciones de pago ----------------
    # tipo_pago (Contado/Crédito = si es a plazos) es distinto de payment_status
    # (Pendiente/Pagada) y payment_method (PayPal/efectivo/…): se muestran los
    # tres para que quede claro el estado real del pago.
    cuotas = list(invoice.cuotas.all()) if invoice.tipo_pago == 'CREDITO' else []
    elements += section('Condiciones de pago')
    if invoice.tipo_pago == 'CREDITO':
        pagadas = sum(1 for c in cuotas if c.estado == 'PAGADA')
        cond = [
            [Paragraph('Tipo de pago:', lbl), f'Crédito a {len(cuotas)} meses'],
            [Paragraph('Cuotas pagadas:', lbl), f'{pagadas} de {len(cuotas)}'],
            [Paragraph('Saldo pendiente:', lbl), _money(invoice.saldo)],
        ]
    else:
        cond = [[Paragraph('Tipo de pago:', lbl), invoice.get_tipo_pago_display()]]
    cond += [
        [Paragraph('Estado de pago:', lbl), invoice.get_payment_status_display()],
        [Paragraph('Método de pago:', lbl),
         invoice.get_payment_method_display() if invoice.payment_method else '—'],
        [Paragraph('Fecha de pago:', lbl), _fecha(invoice.payment_date)],
    ]
    elements += [
        Table(cond, colWidths=[3.5 * cm, usable - 3.5 * cm],
              style=TableStyle([('FONTSIZE', (0, 0), (-1, -1), 9), ('BOTTOMPADDING', (0, 0), (-1, -1), 3)])),
        Spacer(1, 0.4 * cm),
    ]

    # ---------------- Detalle ----------------
    elements += section('Detalle')
    data = [['Producto', 'Cant.', 'P. unit.', 'Subtotal']]
    for d in invoice.details.select_related('product'):
        data.append([d.product.name, str(d.quantity), _money(d.unit_price), _money(d.subtotal)])
    n_lines = invoice.details.count()
    det = Table(data, colWidths=[usable - 8.5 * cm, 2.5 * cm, 3 * cm, 3 * cm], repeatRows=1)
    det.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor(f'#{HEADER_FILL}')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('GRID', (0, 0), (-1, -1), 0.4, colors.HexColor('#d7dae6')),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F5F6FB')]),
        ('ALIGN', (1, 0), (-1, -1), 'RIGHT'),
        ('ALIGN', (0, 0), (0, -1), 'LEFT'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 5), ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
    ]))
    elements += [det, Spacer(1, 0.3 * cm)]

    # ---------------- Totales (caja resaltada a la derecha) ----------------
    tot = Table([
        ['Subtotal', _money(invoice.subtotal)],
        ['IVA (15%)', _money(invoice.tax)],
        ['TOTAL', _money(invoice.total)],
    ], colWidths=[3.5 * cm, 3 * cm], hAlign='RIGHT')
    tot.setStyle(TableStyle([
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
        ('LINEABOVE', (0, 0), (-1, 0), 0.4, colors.HexColor('#d7dae6')),
        ('BACKGROUND', (0, 2), (-1, 2), colors.HexColor(f'#{ACCENT}')),
        ('TEXTCOLOR', (0, 2), (-1, 2), colors.white),
        ('FONTNAME', (0, 2), (-1, 2), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 2), (-1, 2), 11),
        ('TOPPADDING', (0, 0), (-1, -1), 5), ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ('LEFTPADDING', (0, 0), (-1, -1), 8), ('RIGHTPADDING', (0, 0), (-1, -1), 8),
    ]))
    elements += [tot, Spacer(1, 0.4 * cm)]

    # ---------------- Plan de cuotas (si es crédito) ----------------
    if invoice.tipo_pago == 'CREDITO' and cuotas:
        elements += section(f'Plan de cuotas ({len(cuotas)} meses)')
        cdata = [['#', 'Vencimiento', 'Valor', 'Saldo', 'Estado']]
        for c in cuotas:
            cdata.append([str(c.numero), _fecha_corta(c.fecha_vencimiento),
                          _money(c.valor), _money(c.saldo), c.get_estado_display()])
        cstyle = [
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor(f'#{HEADER_FILL}')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('GRID', (0, 0), (-1, -1), 0.4, colors.HexColor('#d7dae6')),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F5F6FB')]),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('TOPPADDING', (0, 0), (-1, -1), 4), ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ]
        for i, c in enumerate(cuotas, start=1):
            col = '1F9D57' if c.estado == 'PAGADA' else 'E0A008'
            cstyle.append(('TEXTCOLOR', (4, i), (4, i), colors.HexColor(f'#{col}')))
            cstyle.append(('FONTNAME', (4, i), (4, i), 'Helvetica-Bold'))
        ctable = Table(cdata, colWidths=[1.4 * cm, 3.4 * cm, 3 * cm, 3 * cm, usable - 10.8 * cm], repeatRows=1)
        ctable.setStyle(TableStyle(cstyle))
        elements += [ctable, Spacer(1, 0.4 * cm)]

    elements.append(Paragraph(
        'Documento generado electrónicamente por Sales System — ejercicio académico, '
        'sin validez tributaria real (proceso del SRI simulado, no emitido ante el SRI).', small))

    doc.build(elements)
    return buffer.getvalue()


def ride_pdf_response(invoice):
    stamp = timezone.localtime().strftime('%Y%m%d_%H%M')
    num = (invoice.numero_factura or f'ID{invoice.id}').replace('-', '')
    response = HttpResponse(build_ride_pdf_bytes(invoice), content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="RIDE_{num}_{stamp}.pdf"'
    return response
