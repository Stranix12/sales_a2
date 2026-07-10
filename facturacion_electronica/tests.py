"""Suite de facturacion_electronica: generación del XML del SRI, máquina de
estados del comprobante, descargas (XML/RIDE) y permisos.

Corre con: python manage.py test facturacion_electronica
"""
from decimal import Decimal

from django.contrib.auth.models import Group, User
from django.core.management import call_command
from django.test import Client, TestCase
from lxml import etree

from billing.models import Invoice
from billing.electronic import asignar_datos_electronicos, _digito_verificador_mod11
from billing.tests import _make_catalog

from .models import ComprobanteElectronico
from .ride import build_ride_pdf_bytes, _money
from .services import generar_comprobante, avanzar_estado, procesar_todo
from .xml_builder import generar_xml_factura


class MoneyFormatTests(TestCase):
    def test_money_siempre_dos_decimales(self):
        # Un IVA recién calculado (subtotal*0.15) puede traer 4 decimales.
        self.assertEqual(_money(Decimal('3.0000')), '$3.00')
        self.assertEqual(_money(Decimal('23.0000')), '$23.00')
        self.assertEqual(_money(Decimal('20')), '$20.00')
        self.assertEqual(_money(Decimal('19.166')), '$19.17')
        self.assertEqual(_money(None), '$0.00')


def _factura(customer, total='57.50', subtotal='50.00', tax='7.50'):
    inv = Invoice.objects.create(customer=customer, subtotal=Decimal(subtotal),
                                 tax=Decimal(tax), total=Decimal(total))
    asignar_datos_electronicos(inv)
    return inv


# =====================================================================
# Generación del XML
# =====================================================================
class XmlBuilderTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.brand, cls.group, cls.supplier, cls.product, cls.customer = _make_catalog()

    def _factura_con_detalle(self):
        inv = _factura(self.customer)
        inv.details.create(product=self.product, quantity=5, unit_price=Decimal('10.00'), subtotal=Decimal('50.00'))
        return inv

    def test_xml_tiene_estructura_del_sri(self):
        inv = self._factura_con_detalle()
        xml = generar_xml_factura(inv)
        root = etree.fromstring(xml.encode('utf-8'))
        self.assertEqual(root.tag, 'factura')
        self.assertEqual(root.get('version'), '1.1.0')
        self.assertIsNotNone(root.find('infoTributaria'))
        self.assertIsNotNone(root.find('infoFactura'))
        self.assertIsNotNone(root.find('detalles/detalle'))

    def test_importe_total_coincide_con_la_factura(self):
        inv = self._factura_con_detalle()
        root = etree.fromstring(generar_xml_factura(inv).encode('utf-8'))
        self.assertEqual(root.findtext('infoFactura/importeTotal'), '57.50')
        self.assertEqual(root.findtext('infoTributaria/claveAcceso'), inv.clave_acceso)

    def test_clave_de_acceso_49_digitos_con_verificador_correcto(self):
        inv = self._factura_con_detalle()
        clave = inv.clave_acceso
        self.assertEqual(len(clave), 49)
        self.assertEqual(clave[-1], _digito_verificador_mod11(clave[:48]))


# =====================================================================
# Máquina de estados
# =====================================================================
class MaquinaEstadosTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.brand, cls.group, cls.supplier, cls.product, cls.customer = _make_catalog()

    def setUp(self):
        self.invoice = _factura(self.customer)
        self.invoice.details.create(product=self.product, quantity=5, unit_price=Decimal('10.00'), subtotal=Decimal('50.00'))

    def test_generar_crea_comprobante_en_estado_generado(self):
        comp = generar_comprobante(self.invoice)
        self.assertEqual(comp.estado, ComprobanteElectronico.GENERADO)
        self.assertTrue(comp.xml_generado)
        self.assertEqual(comp.clave_acceso, self.invoice.clave_acceso)

    def test_generar_es_idempotente(self):
        c1 = generar_comprobante(self.invoice)
        c2 = generar_comprobante(self.invoice)
        self.assertEqual(c1.pk, c2.pk)
        self.assertEqual(ComprobanteElectronico.objects.filter(invoice=self.invoice).count(), 1)

    def test_ciclo_completo_avanza_hasta_autorizado(self):
        comp = generar_comprobante(self.invoice)
        avanzar_estado(comp); comp.refresh_from_db()
        self.assertEqual(comp.estado, ComprobanteElectronico.FIRMADO)
        avanzar_estado(comp); comp.refresh_from_db()
        self.assertEqual(comp.estado, ComprobanteElectronico.RECIBIDO)
        avanzar_estado(comp); comp.refresh_from_db()
        self.assertEqual(comp.estado, ComprobanteElectronico.AUTORIZADO)

    def test_firma_inserta_bloque_signature(self):
        comp = generar_comprobante(self.invoice)
        avanzar_estado(comp); comp.refresh_from_db()
        self.assertIn('Signature', comp.xml_generado)

    def test_autorizacion_setea_numero_y_fecha_y_xml(self):
        comp = procesar_todo(generar_comprobante(self.invoice))
        self.assertEqual(comp.estado, ComprobanteElectronico.AUTORIZADO)
        self.assertEqual(comp.numero_autorizacion, comp.clave_acceso)
        self.assertIsNotNone(comp.fecha_autorizacion)
        self.assertIn('autorizacion', comp.xml_autorizado)

    def test_avanzar_sobre_autorizado_es_idempotente(self):
        comp = procesar_todo(generar_comprobante(self.invoice))
        avanzar_estado(comp); comp.refresh_from_db()
        self.assertEqual(comp.estado, ComprobanteElectronico.AUTORIZADO)  # no cambia
        self.assertIsNone(comp.siguiente_estado)


# =====================================================================
# RIDE
# =====================================================================
class RideTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.brand, cls.group, cls.supplier, cls.product, cls.customer = _make_catalog()

    def test_ride_genera_pdf_sin_comprobante(self):
        inv = _factura(self.customer)
        inv.details.create(product=self.product, quantity=2, unit_price=Decimal('10.00'), subtotal=Decimal('20.00'))
        pdf = build_ride_pdf_bytes(inv)
        self.assertEqual(pdf[:4], b'%PDF')

    def test_ride_genera_pdf_con_comprobante_autorizado(self):
        inv = _factura(self.customer)
        inv.details.create(product=self.product, quantity=2, unit_price=Decimal('10.00'), subtotal=Decimal('20.00'))
        procesar_todo(generar_comprobante(inv))
        pdf = build_ride_pdf_bytes(inv)
        self.assertEqual(pdf[:4], b'%PDF')


# =====================================================================
# Vistas y permisos
# =====================================================================
class VistasComprobanteTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command('setup_roles')
        cls.brand, cls.group, cls.supplier, cls.product, cls.customer = _make_catalog()
        cls.admin = User.objects.create_superuser('admin_fe', 'a@a.com', 'pass12345')
        cls.comprador = User.objects.create_user('comprador_fe', password='pass12345')
        cls.comprador.groups.add(Group.objects.get(name='Analista de Compras'))

    def setUp(self):
        self.invoice = _factura(self.customer)
        self.invoice.details.create(product=self.product, quantity=5, unit_price=Decimal('10.00'), subtotal=Decimal('50.00'))
        generar_comprobante(self.invoice)

    def test_enviar_al_sri_avanza_estado(self):
        c = Client(); c.force_login(self.admin)
        r = c.post(f'/facturacion/factura/{self.invoice.pk}/enviar-sri/', follow=True)
        self.assertEqual(r.status_code, 200)
        self.invoice.comprobante.refresh_from_db()
        self.assertEqual(self.invoice.comprobante.estado, ComprobanteElectronico.FIRMADO)

    def test_descargar_xml_devuelve_xml(self):
        c = Client(); c.force_login(self.admin)
        r = c.get(f'/facturacion/factura/{self.invoice.pk}/xml/')
        self.assertEqual(r.status_code, 200)
        self.assertIn('xml', r['Content-Type'])
        self.assertIn(b'<factura', r.content)

    def test_descargar_ride_devuelve_pdf(self):
        c = Client(); c.force_login(self.admin)
        r = c.get(f'/facturacion/factura/{self.invoice.pk}/ride/')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.content[:4], b'%PDF')

    def test_analista_compras_no_puede_enviar_al_sri(self):
        c = Client(); c.force_login(self.comprador)
        r = c.post(f'/facturacion/factura/{self.invoice.pk}/enviar-sri/')
        self.assertEqual(r.status_code, 403)


# =====================================================================
# Integración con la creación de facturas y el portal del cliente
# =====================================================================
class IntegracionFacturaTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.brand, cls.group, cls.supplier, cls.product, cls.customer = _make_catalog()
        cls.admin = User.objects.create_superuser('admin_int', 'a@a.com', 'pass12345')

    def test_crear_factura_genera_comprobante_en_estado_generado(self):
        c = Client(); c.force_login(self.admin)
        c.post('/invoices/create/', {
            'customer': self.customer.pk,
            'details-TOTAL_FORMS': '1', 'details-INITIAL_FORMS': '0',
            'details-MIN_NUM_FORMS': '0', 'details-MAX_NUM_FORMS': '1000',
            'details-0-product': self.product.pk, 'details-0-quantity': '2', 'details-0-unit_price': '10.00',
        }, follow=True)
        invoice = Invoice.objects.latest('id')
        self.assertTrue(hasattr(invoice, 'comprobante'))
        self.assertEqual(invoice.comprobante.estado, ComprobanteElectronico.GENERADO)


class PortalDescargaComprobanteTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command('setup_roles')
        cls.brand, cls.group, cls.supplier, cls.product, cls.customer = _make_catalog()
        cls.user = User.objects.create_user('cliente_fe', password='pass12345')
        cls.user.groups.add(Group.objects.get(name='Cliente'))
        cls.customer.user = cls.user
        cls.customer.save(update_fields=['user'])
        # Otro cliente + su factura, para verificar el aislamiento por fila.
        cls.otro = User.objects.create_user('otro_fe', password='pass12345')
        from billing.models import Customer
        cls.otro_customer = Customer.objects.create(dni='0102030405', first_name='Otro', last_name='Cliente')

    def setUp(self):
        self.invoice = _factura(self.customer)
        self.invoice.details.create(product=self.product, quantity=2, unit_price=Decimal('10.00'), subtotal=Decimal('20.00'))
        procesar_todo(generar_comprobante(self.invoice))

    def test_cliente_descarga_ride_de_su_factura(self):
        c = Client(); c.force_login(self.user)
        r = c.get(f'/portal/facturas/{self.invoice.pk}/ride/')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.content[:4], b'%PDF')

    def test_cliente_descarga_xml_de_su_factura(self):
        c = Client(); c.force_login(self.user)
        r = c.get(f'/portal/facturas/{self.invoice.pk}/xml/')
        self.assertEqual(r.status_code, 200)
        self.assertIn(b'autorizacion', r.content)

    def test_cliente_no_accede_a_factura_ajena(self):
        otra = _factura(self.otro_customer)
        c = Client(); c.force_login(self.user)
        self.assertEqual(c.get(f'/portal/facturas/{otra.pk}/ride/').status_code, 404)
        self.assertEqual(c.get(f'/portal/facturas/{otra.pk}/xml/').status_code, 404)
