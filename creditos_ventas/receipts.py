"""Comprobante de pago de una cuota de venta — un PDF imprimible por cada
abono registrado, distinto del PDF completo de la factura
(ver billing.invoice_export).

Diseño: banda de cabecera con la marca + N.º de comprobante, datos de la
contraparte e información del crédito lado a lado, detalle de la cuota pagada
(cabecera verde) y estado del crédito con barra de progreso. Usa la misma
paleta que el RIDE (facturacion_electronica.ride) para mantener coherencia.
El constructor _build_receipt_pdf está parametrizado por contraparte y datos
del crédito porque creditos_compras lo reutiliza para el recibo de compras."""
from decimal import Decimal, ROUND_HALF_UP
from io import BytesIO

from django.conf import settings
from django.http import HttpResponse
from django.utils import timezone

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

ACCENT = '33459B'
ACCENT_DARK = '232A5C'
GREEN = '1F9D57'
LIGHT_GREEN = 'E8F6EE'
BORDER = 'cdd4f3'
BAR_EMPTY = 'E2E5F0'


def _money(valor):
    """'$0.00' siempre con 2 decimales, venga como venga el Decimal."""
    return f'${Decimal(valor or 0).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)}'


def _fecha(d):
    return d.strftime('%d/%m/%Y') if d else '—'


def _progress_bar(pct, width):
    """Barra de avance del crédito: tramo pagado en verde, resto en gris."""
    bar_h = 0.45 * cm
    filled = width * min(max(pct, 0), 100) / 100
    if filled < 8 or width - filled < 8:  # casi 0% o casi 100%: un solo tramo
        color = GREEN if filled >= 8 else BAR_EMPTY
        bar = Table([['']], colWidths=[width], rowHeights=[bar_h])
        bar.setStyle(TableStyle([('BACKGROUND', (0, 0), (-1, -1), colors.HexColor(f'#{color}'))]))
        return bar
    bar = Table([['', '']], colWidths=[filled, width - filled], rowHeights=[bar_h])
    bar.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (0, 0), colors.HexColor(f'#{GREEN}')),
        ('BACKGROUND', (1, 0), (1, 0), colors.HexColor(f'#{BAR_EMPTY}')),
    ]))
    return bar


def _build_receipt_pdf(*, numero_comprobante, contraparte_titulo, contraparte_rows,
                       credito_rows, pago, cuota, total_cuotas, total_credito,
                       saldo_documento, cuotas_restantes, proxima_cuota):
    emp = settings.EMPRESA
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        topMargin=1.2 * cm, bottomMargin=1.2 * cm, leftMargin=1.5 * cm, rightMargin=1.5 * cm,
        title=f'Comprobante de pago {numero_comprobante}',
    )
    usable = A4[0] - doc.leftMargin - doc.rightMargin

    styles = getSampleStyleSheet()
    normal = styles['Normal']
    small = ParagraphStyle('small', parent=normal, fontSize=8, leading=10,
                           textColor=colors.HexColor('#5c6474'))
    lbl = ParagraphStyle('lbl', parent=normal, fontName='Helvetica-Bold', fontSize=9)
    val_right = ParagraphStyle('vr', parent=normal, fontSize=9, alignment=2)
    white_big = ParagraphStyle('wb', parent=normal, fontName='Helvetica-Bold', fontSize=16,
                               leading=20, textColor=colors.white)
    white_small = ParagraphStyle('ws', parent=normal, fontSize=9, leading=12, textColor=colors.white)
    badge_style = ParagraphStyle('bg', parent=normal, fontName='Helvetica-Bold', fontSize=11,
                                 leading=14, textColor=colors.white, alignment=1)
    box_hdr = ParagraphStyle('bh', parent=normal, fontName='Helvetica-Bold', fontSize=9,
                             textColor=colors.white)
    stat_lbl = ParagraphStyle('sl', parent=small, alignment=1)
    stat_val = ParagraphStyle('sv', parent=normal, fontName='Helvetica-Bold', fontSize=12,
                              alignment=1, leading=15)
    stat_money = ParagraphStyle('sm', parent=stat_val, fontSize=16, leading=19,
                                textColor=colors.HexColor(f'#{GREEN}'))

    def rows_table(rows, width, value_align=0):
        vstyle = val_right if value_align else normal
        data = [[Paragraph(f'{label}:', lbl),
                 v if not isinstance(v, str) else Paragraph(v, vstyle)] for label, v in rows]
        t = Table(data, colWidths=[width * 0.48, width * 0.52])
        t.setStyle(TableStyle([('FONTSIZE', (0, 0), (-1, -1), 9), ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                               ('BOTTOMPADDING', (0, 0), (-1, -1), 4)]))
        return t

    def boxed(titulo, contenido, width, header_color=ACCENT):
        box = Table([[Paragraph(titulo, box_hdr)], [contenido]], colWidths=[width])
        box.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (0, 0), colors.HexColor(f'#{header_color}')),
            ('BOX', (0, 0), (-1, -1), 0.6, colors.HexColor(f'#{BORDER}')),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('TOPPADDING', (0, 0), (0, 0), 6), ('BOTTOMPADDING', (0, 0), (0, 0), 6),
            ('TOPPADDING', (0, 1), (0, 1), 8), ('BOTTOMPADDING', (0, 1), (0, 1), 8),
            ('LEFTPADDING', (0, 0), (-1, -1), 10), ('RIGHTPADDING', (0, 0), (-1, -1), 10),
        ]))
        return box

    elements = []

    # ---------------- Banda de cabecera (marca + N.º de comprobante) ----------------
    badge = Table([[Paragraph(f'Comprobante N.º<br/>{numero_comprobante}', badge_style)]],
                  colWidths=[4.6 * cm])
    badge.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor(f'#{ACCENT_DARK}')),
        ('TOPPADDING', (0, 0), (-1, -1), 7), ('BOTTOMPADDING', (0, 0), (-1, -1), 7),
    ]))
    header = Table([[
        [Paragraph(emp['nombre'], white_big),
         Paragraph('COMPROBANTE DE PAGO DE CUOTA', white_small)],
        badge,
    ]], colWidths=[usable * 0.66, usable * 0.34])
    header.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor(f'#{ACCENT}')),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('ALIGN', (1, 0), (1, 0), 'RIGHT'),
        ('TOPPADDING', (0, 0), (-1, -1), 12), ('BOTTOMPADDING', (0, 0), (-1, -1), 12),
        ('LEFTPADDING', (0, 0), (-1, -1), 12), ('RIGHTPADDING', (0, 0), (-1, -1), 12),
    ]))
    contacto = Paragraph(
        f"RUC: {emp['ruc']} &nbsp;·&nbsp; {emp['direccion']} &nbsp;·&nbsp; "
        f"Tel: {emp['telefono']} &nbsp;·&nbsp; {emp['email']}",
        ParagraphStyle('cont', parent=small, alignment=1))
    elements += [header, Spacer(1, 0.18 * cm), contacto, Spacer(1, 0.45 * cm)]

    # ---------------- Contraparte + información del crédito (lado a lado) ----------------
    half = usable * 0.485
    inner = half - 20  # ancho útil dentro de la caja (padding 10 por lado)
    dos_cajas = Table([[
        boxed(contraparte_titulo, rows_table(contraparte_rows, inner), half),
        '',
        boxed('INFORMACIÓN DEL CRÉDITO', rows_table(credito_rows, inner), half),
    ]], colWidths=[half, usable * 0.03, half])
    dos_cajas.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 0), ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ('TOPPADDING', (0, 0), (-1, -1), 0), ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
    ]))
    elements += [dos_cajas, Spacer(1, 0.45 * cm)]

    # ---------------- Detalle de la cuota pagada ----------------
    stats = Table([[
        [Paragraph('Cuota N.º', stat_lbl), Spacer(1, 2), Paragraph(f'{cuota.numero} de {total_cuotas}', stat_val)],
        [Paragraph('Fecha de pago', stat_lbl), Spacer(1, 2), Paragraph(_fecha(pago.fecha), stat_val)],
        [Paragraph('Valor pagado', stat_lbl), Spacer(1, 2), Paragraph(_money(pago.valor), stat_money)],
    ]], colWidths=[(usable - 20) / 3] * 3)
    stats.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('LINEBEFORE', (1, 0), (2, 0), 0.6, colors.HexColor(f'#{BORDER}')),
        ('TOPPADDING', (0, 0), (-1, -1), 6), ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
    ]))
    saldo_cuota = Paragraph(
        f'Saldo de esta cuota: <b>{_money(cuota.saldo)}</b>'
        + ('' if cuota.saldo else ' &nbsp;·&nbsp; <font color="#1F9D57"><b>CUOTA PAGADA</b></font>'),
        ParagraphStyle('sc', parent=small, alignment=1))
    elements += [boxed('DETALLE DE LA CUOTA PAGADA', [stats, Spacer(1, 4), saldo_cuota],
                       usable, header_color=GREEN), Spacer(1, 0.45 * cm)]

    # ---------------- Estado del crédito (progreso + resumen) ----------------
    pagado = total_credito - saldo_documento
    pct = int((pagado / total_credito * 100).quantize(Decimal('1'), rounding=ROUND_HALF_UP)) if total_credito else 0
    estado_rows = [
        ('Total del crédito', _money(total_credito)),
        ('Total pagado hasta hoy', Paragraph(f'<font color="#1F9D57"><b>{_money(pagado)}</b></font>', val_right)),
        ('Saldo pendiente', _money(saldo_documento)),
        ('Cuotas restantes', str(cuotas_restantes)),
        ('Próxima cuota', _fecha(proxima_cuota)),
    ]
    progreso = [
        Paragraph(f'<font color="#1F9D57"><b>{pct}% PAGADO</b></font>',
                  ParagraphStyle('pp', parent=normal, fontSize=9)),
        Spacer(1, 3),
        _progress_bar(pct, usable - 20),
        Spacer(1, 8),
        rows_table(estado_rows, usable - 20, value_align=1),
    ]
    elements += [boxed('ESTADO DEL CRÉDITO', progreso, usable), Spacer(1, 0.45 * cm)]

    # ---------------- Observaciones (si el pago las tiene) ----------------
    if pago.observacion:
        obs = boxed('OBSERVACIONES', Paragraph(pago.observacion, normal), usable,
                    header_color='B9790F')
        elements += [obs, Spacer(1, 0.45 * cm)]

    # ---------------- Pie ----------------
    emitido = timezone.localtime().strftime('%d/%m/%Y %H:%M')
    pie = Table([[
        Paragraph('Comprobante generado electrónicamente por Sales System — ejercicio '
                  'académico, sin validez tributaria real.', white_small),
        Paragraph(f'Emitido: {emitido}', ParagraphStyle('em', parent=white_small, alignment=2)),
    ]], colWidths=[usable * 0.68, usable * 0.32])
    pie.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor(f'#{ACCENT_DARK}')),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 8), ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('LEFTPADDING', (0, 0), (-1, -1), 12), ('RIGHTPADDING', (0, 0), (-1, -1), 12),
    ]))
    elements.append(pie)

    doc.build(elements)
    return buffer.getvalue()


def _resumen_credito(cuotas, saldo_documento):
    """Totales del plan: (total, restantes, próxima fecha de vencimiento pendiente)."""
    total = sum((c.valor for c in cuotas), Decimal('0'))
    pendientes = [c for c in cuotas if c.estado != 'PAGADA']
    proxima = min((c.fecha_vencimiento for c in pendientes), default=None)
    return total, len(pendientes), proxima


def build_pago_cuota_venta_pdf_bytes(pago):
    cuota = pago.cuota
    invoice = cuota.factura
    cust = invoice.customer
    cuotas = list(invoice.cuotas.all())
    total_credito, restantes, proxima = _resumen_credito(cuotas, invoice.saldo)
    return _build_receipt_pdf(
        numero_comprobante=f'CP-{pago.pk:06d}',
        contraparte_titulo='DATOS DEL CLIENTE',
        contraparte_rows=[
            ('Nombre', cust.full_name),
            ('Cédula/RUC', cust.dni),
            ('Correo', cust.email or '—'),
            ('Teléfono', cust.phone or '—'),
        ],
        credito_rows=[
            ('N.º de factura', invoice.numero_factura or f'#{invoice.pk}'),
            ('Fecha de emisión', _fecha(invoice.invoice_date)),
            ('Forma de pago', f'Crédito a {len(cuotas)} meses'),
            ('Total del documento', _money(invoice.total)),
        ],
        pago=pago, cuota=cuota, total_cuotas=len(cuotas), total_credito=total_credito,
        saldo_documento=invoice.saldo, cuotas_restantes=restantes, proxima_cuota=proxima,
    )


def _response(pdf_bytes, filename):
    response = HttpResponse(pdf_bytes, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


def pago_cuota_venta_pdf_response(pago):
    stamp = timezone.localtime().strftime('%Y%m%d_%H%M')
    filename = f'Recibo_Factura{pago.cuota.factura_id}_Cuota{pago.cuota.numero}_{stamp}.pdf'
    return _response(build_pago_cuota_venta_pdf_bytes(pago), filename)
