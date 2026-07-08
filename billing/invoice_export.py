"""PDF de una factura electrónica (comprobante individual).

Reutiliza el mismo estándar visual de ``purchasing.exports`` /
``billing.mixins.ExportListMixin`` (cabecera `#343A40`, filas alternas,
marca de tiempo) pero con formato de **factura**: datos del emisor
(``settings.EMPRESA``), del cliente, líneas, totales, estado de pago y la
clave de acceso simulada.

Expone:
  - ``build_invoice_pdf_bytes(invoice)`` -> bytes  (para adjuntar al correo)
  - ``invoice_pdf_response(invoice)``   -> HttpResponse (descarga)
"""
from io import BytesIO

from django.conf import settings
from django.http import HttpResponse
from django.utils import timezone

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

HEADER_FILL = '343A40'
ACCENT = '33459B'
_ESTADO_COLOR = {'PAGADA': '1F9D57', 'PENDIENTE': 'E0A008', 'ANULADA': 'D64550'}


def _fecha(dt):
    return timezone.localtime(dt).strftime('%d/%m/%Y %H:%M') if dt else '—'


def build_invoice_pdf_bytes(invoice):
    emp = settings.EMPRESA
    cust = invoice.customer
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        topMargin=1.4 * cm, bottomMargin=1.4 * cm, leftMargin=1.5 * cm, rightMargin=1.5 * cm,
        title=f'Factura {invoice.numero_factura or invoice.id}',
    )
    styles = getSampleStyleSheet()
    normal = styles['Normal']
    small = ParagraphStyle('small', parent=normal, fontSize=8, leading=10, textColor=colors.HexColor('#5c6474'))
    lbl = ParagraphStyle('lbl', parent=normal, fontName='Helvetica-Bold', fontSize=9)
    emisor_name = ParagraphStyle('emp', parent=normal, fontName='Helvetica-Bold', fontSize=13,
                                 textColor=colors.HexColor(f'#{ACCENT}'))
    doc_title = ParagraphStyle('doc', parent=normal, fontName='Helvetica-Bold', fontSize=15, alignment=2)
    mono = ParagraphStyle('mono', parent=normal, fontName='Courier', fontSize=8)
    estado = invoice.payment_status
    estado_color = _ESTADO_COLOR.get(estado, '5c6474')
    estado_style = ParagraphStyle('est', parent=normal, fontName='Helvetica-Bold', fontSize=10,
                                  alignment=2, textColor=colors.HexColor(f'#{estado_color}'))

    # --- Cabecera: emisor (izq) + FACTURA (der) ---
    emisor_block = [
        Paragraph(emp['nombre'], emisor_name),
        Paragraph(f"RUC: {emp['ruc']}", small),
        Paragraph(emp['direccion'], small),
        Paragraph(f"Tel: {emp['telefono']} · {emp['email']}", small),
    ]
    factura_block = [
        Paragraph('FACTURA', doc_title),
        Paragraph(f"N.º {invoice.numero_factura or '—'}", ParagraphStyle('n', parent=normal, alignment=2, fontSize=10)),
        Paragraph(f"Fecha: {_fecha(invoice.invoice_date)}", ParagraphStyle('f', parent=small, alignment=2)),
        Paragraph(f"Estado: {invoice.get_payment_status_display().upper()}", estado_style),
    ]
    header = Table([[emisor_block, factura_block]], colWidths=[10.5 * cm, 6.5 * cm])
    header.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'TOP')]))

    elements = [
        header,
        Spacer(1, 0.3 * cm),
        Table([[Paragraph('Clave de acceso:', lbl), Paragraph(invoice.clave_acceso or '—', mono)]],
              colWidths=[3.2 * cm, 13.3 * cm],
              style=TableStyle([('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#F2F4F9')),
                                ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor('#e1e4ec')),
                                ('TOPPADDING', (0, 0), (-1, -1), 5), ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
                                ('LEFTPADDING', (0, 0), (-1, -1), 8)])),
        Spacer(1, 0.4 * cm),
        # --- Cliente ---
        Table([
            [Paragraph('Cliente:', lbl), cust.full_name, Paragraph('DNI/RUC:', lbl), cust.dni],
            [Paragraph('Dirección:', lbl), cust.address or '—', Paragraph('Email:', lbl), cust.email or '—'],
        ], colWidths=[2.4 * cm, 6.6 * cm, 2.4 * cm, 5.1 * cm],
            style=TableStyle([('VALIGN', (0, 0), (-1, -1), 'TOP'), ('FONTSIZE', (0, 0), (-1, -1), 9),
                              ('BOTTOMPADDING', (0, 0), (-1, -1), 4)])),
        Spacer(1, 0.5 * cm),
    ]

    # --- Detalle ---
    data = [['Producto', 'Cantidad', 'Precio unit.', 'Subtotal']]
    for d in invoice.details.select_related('product'):
        data.append([d.product.name, str(d.quantity), f'${d.unit_price}', f'${d.subtotal}'])
    data.append(['', '', 'Subtotal', f'${invoice.subtotal}'])
    data.append(['', '', 'IVA (15%)', f'${invoice.tax}'])
    data.append(['', '', 'TOTAL', f'${invoice.total}'])

    n_lines = invoice.details.count()
    table = Table(data, colWidths=[8 * cm, 2.7 * cm, 3 * cm, 3 * cm], repeatRows=1)
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor(f'#{HEADER_FILL}')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('ROWBACKGROUNDS', (0, 1), (-1, n_lines), [colors.white, colors.HexColor('#F2F2F2')]),
        ('ALIGN', (1, 0), (-1, -1), 'RIGHT'),
        ('FONTNAME', (2, -1), (-1, -1), 'Helvetica-Bold'),
        ('SPAN', (0, -3), (1, -3)), ('SPAN', (0, -2), (1, -2)), ('SPAN', (0, -1), (1, -1)),
        ('LINEABOVE', (2, -1), (-1, -1), 1, colors.black),
        ('TOPPADDING', (0, 0), (-1, -1), 5), ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
    ]))
    elements += [table, Spacer(1, 0.5 * cm)]

    # --- Información de pago ---
    pago = [
        [Paragraph('Estado de pago:', lbl), invoice.get_payment_status_display()],
        [Paragraph('Método:', lbl), invoice.get_payment_method_display() if invoice.payment_method else '—'],
        [Paragraph('Fecha de pago:', lbl), _fecha(invoice.payment_date)],
    ]
    elements.append(Table(pago, colWidths=[3.5 * cm, 6 * cm],
                          style=TableStyle([('FONTSIZE', (0, 0), (-1, -1), 9)])))
    elements += [
        Spacer(1, 0.6 * cm),
        Paragraph('Documento generado electrónicamente por Sales System — ejercicio académico, '
                  'sin validez tributaria real (no emitido ante el SRI).', small),
    ]

    doc.build(elements)
    return buffer.getvalue()


def _filename(invoice):
    stamp = timezone.localtime().strftime('%Y%m%d_%H%M')
    num = (invoice.numero_factura or f'ID{invoice.id}').replace('-', '')
    return f'Factura_{num}_{stamp}.pdf'


def invoice_pdf_response(invoice):
    response = HttpResponse(build_invoice_pdf_bytes(invoice), content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="{_filename(invoice)}"'
    return response
