"""Tests del reporte de IVA por período (billing/reports.py + vistas en
billing/views.py): desglose por tarifa (15%/0%), filtro de fechas, permisos
y descargas PDF/Excel.

Corre con: python manage.py test billing.tests_reports
"""
from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth.models import Group, User
from django.core.management import call_command
from django.test import Client, TestCase
from django.utils import timezone

from .models import Brand, Customer, Invoice, InvoiceDetail, Product, ProductGroup
from .pricing import calcular_subtotal_iva, desglose_iva_por_tarifa


def _catalogo_iva():
    brand = Brand.objects.create(name='Marca RepIVA')
    group = ProductGroup.objects.create(name='Grupo RepIVA')
    p15 = Product.objects.create(name='RepGravado', brand=brand, group=group,
                                 unit_price=Decimal('20.00'), stock=10, is_active=True, iva_tarifa_0=False)
    p0 = Product.objects.create(name='RepExento', brand=brand, group=group,
                                unit_price=Decimal('10.00'), stock=10, is_active=True, iva_tarifa_0=True)
    customer = Customer.objects.create(dni='1710035006', first_name='Rep', last_name='Iva')
    return brand, group, p15, p0, customer


def _crear_factura(customer, p15, p0, fecha=None):
    """Factura con 1 línea gravada ($20 -> IVA $3.00) + 1 exenta ($10)."""
    inv = Invoice.objects.create(customer=customer)
    InvoiceDetail.objects.create(invoice=inv, product=p15, quantity=1, unit_price=Decimal('20.00'))
    InvoiceDetail.objects.create(invoice=inv, product=p0, quantity=1, unit_price=Decimal('10.00'))
    details = list(inv.details.select_related('product'))
    inv.subtotal, inv.tax = calcular_subtotal_iva((d.product, d.subtotal) for d in details)
    inv.total = inv.subtotal + inv.tax
    inv.save()
    if fecha:
        Invoice.objects.filter(pk=inv.pk).update(invoice_date=fecha)
        inv.refresh_from_db()
    return inv


class DesgloseIvaPorTarifaTests(TestCase):
    """El cálculo puro (sin BD) que alimenta el reporte."""

    def test_desglose_mixto(self):
        class P:
            def __init__(self, exento): self.iva_tarifa_0 = exento
        desglose = desglose_iva_por_tarifa([(P(False), Decimal('20.00')), (P(True), Decimal('10.00'))])
        self.assertEqual(desglose['base_15'], Decimal('20.00'))
        self.assertEqual(desglose['iva_15'], Decimal('3.00'))
        self.assertEqual(desglose['base_0'], Decimal('10.00'))
        self.assertEqual(desglose['total_base'], Decimal('30.00'))
        self.assertEqual(desglose['total_iva'], Decimal('3.00'))
        self.assertEqual(desglose['total'], Decimal('33.00'))

    def test_desglose_vacio_no_revienta(self):
        desglose = desglose_iva_por_tarifa([])
        self.assertEqual(desglose['total'], Decimal('0'))


class IvaReportViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.brand, cls.group, cls.p15, cls.p0, cls.customer = _catalogo_iva()
        cls.admin = User.objects.create_superuser('admin_repiva', 'a@a.com', 'pass12345')

    def setUp(self):
        self.client = Client()
        self.client.force_login(self.admin)

    def test_reporte_vacio_no_revienta(self):
        r = self.client.get('/invoices/reporte-iva/')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.context['totales']['total'], Decimal('0'))

    def test_totales_correctos_con_factura_mixta(self):
        _crear_factura(self.customer, self.p15, self.p0)
        r = self.client.get('/invoices/reporte-iva/')
        totales = r.context['totales']
        self.assertEqual(totales['base_15'], Decimal('20.00'))
        self.assertEqual(totales['iva_15'], Decimal('3.00'))
        self.assertEqual(totales['base_0'], Decimal('10.00'))
        self.assertEqual(totales['total'], Decimal('33.00'))
        self.assertEqual(len(r.context['filas']), 1)

    def test_varias_facturas_se_suman(self):
        _crear_factura(self.customer, self.p15, self.p0)
        _crear_factura(self.customer, self.p15, self.p0)
        r = self.client.get('/invoices/reporte-iva/')
        totales = r.context['totales']
        self.assertEqual(totales['base_15'], Decimal('40.00'))
        self.assertEqual(totales['iva_15'], Decimal('6.00'))
        self.assertEqual(totales['total'], Decimal('66.00'))
        self.assertEqual(len(r.context['filas']), 2)

    def test_filtro_de_fechas_excluye_fuera_de_rango(self):
        hoy = timezone.now()
        lejos = hoy - timedelta(days=200)
        _crear_factura(self.customer, self.p15, self.p0, fecha=lejos)
        r = self.client.get('/invoices/reporte-iva/')  # por defecto: mes actual
        self.assertEqual(len(r.context['filas']), 0)
        self.assertEqual(r.context['totales']['total'], Decimal('0'))

    def test_filtro_de_fechas_incluye_dentro_de_rango(self):
        hoy = timezone.now()
        lejos = hoy - timedelta(days=200)
        _crear_factura(self.customer, self.p15, self.p0, fecha=lejos)
        d_desde = (lejos - timedelta(days=1)).date().isoformat()
        d_hasta = (lejos + timedelta(days=1)).date().isoformat()
        r = self.client.get(f'/invoices/reporte-iva/?date_from={d_desde}&date_to={d_hasta}')
        self.assertEqual(len(r.context['filas']), 1)
        self.assertEqual(r.context['totales']['total'], Decimal('33.00'))

    def test_factura_solo_exenta_no_aporta_iva(self):
        inv = Invoice.objects.create(customer=self.customer)
        InvoiceDetail.objects.create(invoice=inv, product=self.p0, quantity=1, unit_price=Decimal('10.00'))
        details = list(inv.details.select_related('product'))
        inv.subtotal, inv.tax = calcular_subtotal_iva((d.product, d.subtotal) for d in details)
        inv.total = inv.subtotal + inv.tax
        inv.save()
        r = self.client.get('/invoices/reporte-iva/')
        totales = r.context['totales']
        self.assertEqual(totales['iva_15'], Decimal('0'))
        self.assertEqual(totales['base_0'], Decimal('10.00'))
        self.assertEqual(totales['total'], Decimal('10.00'))

    def test_descarga_pdf(self):
        _crear_factura(self.customer, self.p15, self.p0)
        r = self.client.get('/invoices/reporte-iva/pdf/')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.content[:4], b'%PDF')
        self.assertIn('attachment', r['Content-Disposition'])

    def test_descarga_excel(self):
        _crear_factura(self.customer, self.p15, self.p0)
        r = self.client.get('/invoices/reporte-iva/excel/')
        self.assertEqual(r.status_code, 200)
        self.assertIn('spreadsheetml', r['Content-Type'])

    def test_boton_visible_en_listado_de_facturas(self):
        r = self.client.get('/invoices/')
        self.assertIn('Reporte de IVA', r.content.decode())

    def test_fecha_desde_posterior_a_hasta_es_invalida(self):
        r = self.client.get('/invoices/reporte-iva/?date_from=2026-06-30&date_to=2026-06-01')
        self.assertEqual(r.status_code, 200)
        self.assertFalse(r.context['form'].is_valid())
        # Con el form invalido, cae al default (mes actual) en vez de reventar.
        self.assertIsNotNone(r.context['date_from'])


class IvaReportPermissionTests(TestCase):
    """Requiere billing.view_invoice -- ni mas ni menos que ver facturas."""
    @classmethod
    def setUpTestData(cls):
        call_command('setup_roles')
        cls.brand, cls.group, cls.p15, cls.p0, cls.customer = _catalogo_iva()

    def test_analista_de_compras_no_ve_el_reporte(self):
        u = User.objects.create_user('analista_repiva', password='x')
        u.groups.add(Group.objects.get(name='Analista de Compras'))
        c = Client(); c.force_login(u)
        r = c.get('/invoices/reporte-iva/')
        self.assertEqual(r.status_code, 403)

    def test_vendedor_ve_el_reporte(self):
        u = User.objects.create_user('vendedor_repiva', password='x')
        u.groups.add(Group.objects.get(name='Vendedor'))
        c = Client(); c.force_login(u)
        r = c.get('/invoices/reporte-iva/')
        self.assertEqual(r.status_code, 200)
