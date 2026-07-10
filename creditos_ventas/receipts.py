"""Comprobante de pago de una cuota (venta o compra) — un PDF chico e
imprimible por cada abono registrado, distinto del PDF completo de la
factura/compra (ver billing.invoice_export / purchasing.exports)."""
from io import BytesIO

from django.conf import settings
from django.http import HttpResponse
from django.utils import timezone

from reportlab.lib import colors
from reportlab.lib.pagesizes import A5
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import HRFlowable, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

ACCENT = '33459B'


def _fecha(d):
    return d.strftime('%d/%m/%Y') if d else '—'


def _build_receipt_pdf(*, documento_titulo, contraparte_label, contraparte, pago, cuota, saldo_documento):
    emp = settings.EMPRESA
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A5,
        topMargin=1.2 * cm, bottomMargin=1.2 * cm, leftMargin=1.3 * cm, rightMargin=1.3 * cm,
        title=f'Comprobante de pago — {documento_titulo}',
    )
    styles = getSampleStyleSheet()
    normal = styles['Normal']
    small = ParagraphStyle('small', parent=normal, fontSize=8, textColor=colors.HexColor('#5c6474'))
    lbl = ParagraphStyle('lbl', parent=normal, fontName='Helvetica-Bold', fontSize=9)
    title_style = ParagraphStyle('t', parent=normal, fontName='Helvetica-Bold', fontSize=14,
                                 textColor=colors.HexColor(f'#{ACCENT}'))
    amount_label = ParagraphStyle('al', parent=lbl, alignment=1)
    big_amount = ParagraphStyle('amt', parent=normal, fontName='Helvetica-Bold', fontSize=22, alignment=1)

    elements = [
        Paragraph(emp['nombre'], ParagraphStyle('emp', parent=normal, fontName='Helvetica-Bold', fontSize=11)),
        Paragraph(f"RUC: {emp['ruc']}", small),
        Spacer(1, 0.3 * cm),
        Paragraph('COMPROBANTE DE PAGO', title_style),
        Paragraph(documento_titulo, small),
        HRFlowable(width='100%', thickness=0.8, color=colors.HexColor(f'#{ACCENT}'), spaceBefore=4, spaceAfter=8),
        Table([
            [Paragraph(f'{contraparte_label}:', lbl), str(contraparte)],
            [Paragraph('Cuota N.º:', lbl), str(cuota.numero)],
            [Paragraph('Fecha de pago:', lbl), _fecha(pago.fecha)],
        ], colWidths=[3.2 * cm, 7.3 * cm], style=TableStyle([('FONTSIZE', (0, 0), (-1, -1), 9),
                                                             ('BOTTOMPADDING', (0, 0), (-1, -1), 3)])),
        Spacer(1, 0.4 * cm),
        Table([
            [Paragraph('MONTO PAGADO', amount_label)],
            [Paragraph(f'${pago.valor}', big_amount)],
        ], colWidths=[10.5 * cm],
            style=TableStyle([('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#EEF0FB')),
                              ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor('#cdd4f3')),
                              ('TOPPADDING', (0, 0), (-1, -1), 6), ('BOTTOMPADDING', (0, 0), (-1, -1), 6)])),
        Spacer(1, 0.4 * cm),
        Table([
            [Paragraph('Saldo de la cuota:', lbl), f'${cuota.saldo}'],
            [Paragraph('Saldo del documento:', lbl), f'${saldo_documento}'],
        ], colWidths=[4 * cm, 6.5 * cm], style=TableStyle([('FONTSIZE', (0, 0), (-1, -1), 9)])),
    ]
    if pago.observacion:
        elements += [Spacer(1, 0.3 * cm), Paragraph('Observación:', lbl), Paragraph(pago.observacion, normal)]
    elements += [
        Spacer(1, 0.6 * cm),
        Paragraph('Comprobante generado electrónicamente por Sales System — ejercicio académico, '
                  'sin validez tributaria real.', small),
    ]

    doc.build(elements)
    return buffer.getvalue()


def build_pago_cuota_venta_pdf_bytes(pago):
    cuota = pago.cuota
    invoice = cuota.factura
    return _build_receipt_pdf(
        documento_titulo=f'Factura {invoice.numero_factura or invoice.pk} — Cuota {cuota.numero} de {invoice.cuotas.count()}',
        contraparte_label='Cliente', contraparte=invoice.customer.full_name,
        pago=pago, cuota=cuota, saldo_documento=invoice.saldo,
    )


def build_pago_cuota_compra_pdf_bytes(pago):
    cuota = pago.cuota
    purchase = cuota.compra
    return _build_receipt_pdf(
        documento_titulo=f'Compra #{purchase.pk} ({purchase.document_number}) — Cuota {cuota.numero} de {purchase.cuotas.count()}',
        contraparte_label='Proveedor', contraparte=str(purchase.supplier),
        pago=pago, cuota=cuota, saldo_documento=purchase.saldo,
    )


def _response(pdf_bytes, filename):
    response = HttpResponse(pdf_bytes, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


def pago_cuota_venta_pdf_response(pago):
    stamp = timezone.localtime().strftime('%Y%m%d_%H%M')
    filename = f'Recibo_Factura{pago.cuota.factura_id}_Cuota{pago.cuota.numero}_{stamp}.pdf'
    return _response(build_pago_cuota_venta_pdf_bytes(pago), filename)


def pago_cuota_compra_pdf_response(pago):
    stamp = timezone.localtime().strftime('%Y%m%d_%H%M')
    filename = f'Recibo_Compra{pago.cuota.compra_id}_Cuota{pago.cuota.numero}_{stamp}.pdf'
    return _response(build_pago_cuota_compra_pdf_bytes(pago), filename)
