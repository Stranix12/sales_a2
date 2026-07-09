"""Suite de tests de billing: validadores de modelo, facturación electrónica,
creación de facturas (stock + concurrencia), pagos (manual y PayPal mockeado)
y aplicación real de permisos por rol.

Corre con: python manage.py test billing
"""
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth.models import Group, User
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.test import Client, TestCase

from . import paypal
from .electronic import _digito_verificador_mod11, generar_clave_acceso, generar_numero_factura
from .models import (
    Brand, Customer, Invoice, InvoiceDetail, PaymentLog, Product, ProductGroup, Supplier,
)
from shared.validators import validate_cedula_ec


def _make_catalog():
    """Datos base reutilizados por casi todos los tests: marca, grupo,
    proveedor, un producto y un cliente."""
    brand = Brand.objects.create(name='Marca X')
    group = ProductGroup.objects.create(name='Grupo X')
    supplier = Supplier.objects.create(name='Proveedor X')
    product = Product.objects.create(
        name='Producto X', brand=brand, group=group,
        unit_price=Decimal('10.00'), stock=20, is_active=True,
    )
    customer = Customer.objects.create(
        dni='1710034065', first_name='Ana', last_name='Torres', email='ana@example.com',
    )
    return brand, group, supplier, product, customer


# =====================================================================
# Validadores de modelo
# =====================================================================
class CedulaValidatorTests(TestCase):
    def test_cedula_valida_pasa(self):
        validate_cedula_ec('1710034065')  # no debe lanzar

    def test_cedula_con_letras_rechazada(self):
        with self.assertRaises(ValidationError):
            validate_cedula_ec('17100A4065')

    def test_cedula_longitud_invalida_rechazada(self):
        with self.assertRaises(ValidationError):
            validate_cedula_ec('12345')

    def test_cedula_digito_verificador_incorrecto_rechazada(self):
        with self.assertRaises(ValidationError):
            validate_cedula_ec('1710034066')  # último dígito alterado


class ModelValidatorTests(TestCase):
    """Los campos numéricos que el usuario llena (stock, precios, cantidad)
    deben rechazar valores negativos o cero a nivel de modelo, no solo en
    el HTML del formulario (min= es solo cosmético del navegador)."""

    @classmethod
    def setUpTestData(cls):
        cls.brand, cls.group, cls.supplier, cls.product, cls.customer = _make_catalog()

    def test_product_stock_negativo_rechazado(self):
        p = Product(name='Y', brand=self.brand, group=self.group,
                    unit_price=Decimal('5.00'), stock=-1)
        with self.assertRaises(ValidationError):
            p.full_clean()

    def test_product_stock_cero_es_valido(self):
        p = Product(name='Y', brand=self.brand, group=self.group,
                    unit_price=Decimal('5.00'), stock=0)
        p.full_clean()  # no debe lanzar: un producto agotado es válido

    def test_product_precio_cero_rechazado(self):
        p = Product(name='Y', brand=self.brand, group=self.group,
                    unit_price=Decimal('0'), stock=5)
        with self.assertRaises(ValidationError):
            p.full_clean()

    def test_invoicedetail_cantidad_negativa_rechazada(self):
        invoice = Invoice.objects.create(customer=self.customer)
        d = InvoiceDetail(invoice=invoice, product=self.product, quantity=-1,
                          unit_price=Decimal('10.00'))
        with self.assertRaises(ValidationError):
            d.full_clean()

    def test_invoicedetail_precio_cero_rechazado(self):
        invoice = Invoice.objects.create(customer=self.customer)
        d = InvoiceDetail(invoice=invoice, product=self.product, quantity=1,
                          unit_price=Decimal('0'))
        with self.assertRaises(ValidationError):
            d.full_clean()


# =====================================================================
# Facturación electrónica simulada
# =====================================================================
class ElectronicInvoicingTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        _, _, _, cls.product, cls.customer = _make_catalog()

    def test_numero_factura_formato(self):
        invoice = Invoice.objects.create(customer=self.customer)
        numero = generar_numero_factura(invoice)
        self.assertEqual(numero, f'001-001-{invoice.pk:09d}')

    def test_clave_acceso_49_digitos_y_verificador_correcto(self):
        invoice = Invoice.objects.create(customer=self.customer)
        clave = generar_clave_acceso(invoice)
        self.assertEqual(len(clave), 49)
        self.assertTrue(clave.isdigit())
        self.assertEqual(_digito_verificador_mod11(clave[:48]), clave[48])

    def test_dos_facturas_distintas_tienen_claves_distintas(self):
        inv1 = Invoice.objects.create(customer=self.customer)
        inv2 = Invoice.objects.create(customer=self.customer)
        self.assertNotEqual(generar_clave_acceso(inv1), generar_clave_acceso(inv2))
        self.assertNotEqual(generar_numero_factura(inv1), generar_numero_factura(inv2))


# =====================================================================
# Creación de facturas: stock, líneas repetidas, validación
# =====================================================================
class InvoiceCreateViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.brand, cls.group, cls.supplier, cls.product, cls.customer = _make_catalog()
        cls.admin = User.objects.create_superuser('admin_test', 'a@a.com', 'pass12345')

    def setUp(self):
        self.client = Client()
        self.client.force_login(self.admin)

    def _post(self, lines, document='F-1'):
        data = {
            'customer': self.customer.pk,
            'details-TOTAL_FORMS': str(len(lines)), 'details-INITIAL_FORMS': '0',
            'details-MIN_NUM_FORMS': '0', 'details-MAX_NUM_FORMS': '1000',
        }
        for i, (product, qty, price) in enumerate(lines):
            data[f'details-{i}-product'] = product.pk if product else ''
            data[f'details-{i}-quantity'] = qty
            data[f'details-{i}-unit_price'] = price
        return self.client.post('/invoices/create/', data, follow=True)

    def test_creacion_normal_descuenta_stock_y_asigna_datos_electronicos(self):
        self._post([(self.product, '3', '10.00')])
        invoice = Invoice.objects.latest('id')
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 17)
        self.assertEqual(invoice.total, Decimal('34.50'))  # 30 + 15% IVA
        self.assertIsNotNone(invoice.numero_factura)
        self.assertEqual(len(invoice.clave_acceso), 49)

    def test_stock_insuficiente_no_crea_factura_ni_descuenta(self):
        before = Invoice.objects.count()
        r = self._post([(self.product, '999', '10.00')])
        self.assertEqual(Invoice.objects.count(), before)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 20)  # intacto
        self.assertIn('insuficiente', r.content.decode().lower())

    def test_mismo_producto_en_dos_lineas_se_suma_para_validar_stock(self):
        # 15 + 10 = 25 > stock (20) -> debe rechazar, aunque cada línea
        # individual sea "válida" por separado.
        before = Invoice.objects.count()
        self._post([(self.product, '15', '10.00'), (self.product, '10', '10.00')])
        self.assertEqual(Invoice.objects.count(), before)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 20)


# =====================================================================
# Pagos: manual y PayPal (mockeado, sin red real)
# =====================================================================
class PaymentTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.brand, cls.group, cls.supplier, cls.product, cls.customer = _make_catalog()
        cls.admin = User.objects.create_superuser('admin_test2', 'a@a.com', 'pass12345')

    def setUp(self):
        self.client = Client()
        self.client.force_login(self.admin)
        self.invoice = Invoice.objects.create(customer=self.customer, total=Decimal('50.00'))

    def test_marcar_como_pagado_manual(self):
        r = self.client.post(f'/invoices/{self.invoice.pk}/mark-paid/',
                             {'payment_method': 'efectivo', 'note': 'test'}, follow=True)
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.payment_status, 'PAGADA')
        self.assertEqual(self.invoice.payment_method, 'efectivo')
        self.assertTrue(PaymentLog.objects.filter(invoice=self.invoice, method='efectivo').exists())

    def test_no_se_puede_pagar_dos_veces(self):
        self.client.post(f'/invoices/{self.invoice.pk}/mark-paid/', {'payment_method': 'efectivo'})
        self.client.post(f'/invoices/{self.invoice.pk}/mark-paid/', {'payment_method': 'tarjeta'})
        self.assertEqual(PaymentLog.objects.filter(invoice=self.invoice).count(), 1)

    def test_metodo_invalido_no_marca_como_pagado(self):
        self.client.post(f'/invoices/{self.invoice.pk}/mark-paid/', {'payment_method': 'bitcoin'})
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.payment_status, 'PENDIENTE')


class PayPalFlowTests(TestCase):
    """Mockea billing.paypal.requests.post: nunca toca la red real."""

    @classmethod
    def setUpTestData(cls):
        cls.brand, cls.group, cls.supplier, cls.product, cls.customer = _make_catalog()
        cls.admin = User.objects.create_superuser('admin_test3', 'a@a.com', 'pass12345')

    def setUp(self):
        self.client = Client()
        self.client.force_login(self.admin)
        self.invoice = Invoice.objects.create(customer=self.customer, total=Decimal('25.00'))

    def test_paypal_no_configurado_muestra_error_sin_crashear(self):
        self.assertFalse(paypal.is_configured())
        r = self.client.post(f'/invoices/{self.invoice.pk}/paypal/start/', follow=True)
        self.assertEqual(r.status_code, 200)
        self.assertIn('no está configurado', r.content.decode())

    @patch.object(paypal.settings, 'PAYPAL_CLIENT_ID', 'fake-id')
    @patch.object(paypal.settings, 'PAYPAL_CLIENT_SECRET', 'fake-secret')
    def test_flujo_completo_create_y_capture(self):
        def fake_post(url, **kwargs):
            class R:
                def __init__(self, data):
                    self._data = data
                def raise_for_status(self):
                    pass
                def json(self):
                    return self._data
            if 'oauth2/token' in url:
                return R({'access_token': 'FAKE'})
            if url.endswith('/v2/checkout/orders'):
                return R({'id': 'ORDER1', 'links': [{'rel': 'approve', 'href': 'https://paypal.test/approve'}]})
            if '/v2/checkout/orders/ORDER1/capture' in url:
                return R({'status': 'COMPLETED',
                          'purchase_units': [{'payments': {'captures': [{'id': 'CAP1'}]}}]})
            raise AssertionError(f'URL inesperada: {url}')

        with patch('billing.paypal.requests.post', side_effect=fake_post):
            r1 = self.client.post(f'/invoices/{self.invoice.pk}/paypal/start/')
            self.assertEqual(r1.status_code, 302)
            self.assertEqual(r1.url, 'https://paypal.test/approve')

            self.client.get(f'/invoices/{self.invoice.pk}/paypal/return/', {'token': 'ORDER1'})

        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.payment_status, 'PAGADA')
        self.assertEqual(self.invoice.payment_method, 'paypal')
        log = PaymentLog.objects.get(invoice=self.invoice)
        self.assertIn('ORDER1', log.note)
        self.assertIn('CAP1', log.note)

    def test_cancelar_no_modifica_la_factura(self):
        self.client.get(f'/invoices/{self.invoice.pk}/paypal/cancel/')
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.payment_status, 'PENDIENTE')


# =====================================================================
# Permisos reales por rol
# =====================================================================
class RolePermissionTests(TestCase):
    """setup_roles crea los grupos con sus permisos; aquí se verifica que
    las vistas realmente los apliquen (no solo que existan en la BD)."""

    @classmethod
    def setUpTestData(cls):
        call_command('setup_roles')
        cls.vendedor = User.objects.create_user('vendedor_t', password='pass12345')
        cls.vendedor.groups.add(Group.objects.get(name='Vendedor'))
        cls.comprador = User.objects.create_user('comprador_t', password='pass12345')
        cls.comprador.groups.add(Group.objects.get(name='Analista de Compras'))
        cls.admin = User.objects.create_superuser('admin_t', 'a@a.com', 'pass12345')

    def test_anonimo_redirige_a_login(self):
        r = Client().get('/invoices/')
        self.assertEqual(r.status_code, 302)

    def test_vendedor_accede_a_clientes_y_facturas(self):
        c = Client(); c.force_login(self.vendedor)
        self.assertEqual(c.get('/customers/').status_code, 200)
        self.assertEqual(c.get('/invoices/').status_code, 200)

    def test_vendedor_no_accede_a_catalogo_ni_compras(self):
        c = Client(); c.force_login(self.vendedor)
        self.assertEqual(c.get('/brands/create/').status_code, 403)
        self.assertEqual(c.get('/products/create/').status_code, 403)
        self.assertEqual(c.get('/purchases/').status_code, 403)

    def test_analista_compras_accede_a_catalogo_y_compras(self):
        c = Client(); c.force_login(self.comprador)
        self.assertEqual(c.get('/brands/').status_code, 200)
        self.assertEqual(c.get('/products/create/').status_code, 200)
        self.assertEqual(c.get('/purchases/').status_code, 200)

    def test_analista_compras_no_accede_a_clientes_ni_facturas(self):
        c = Client(); c.force_login(self.comprador)
        self.assertEqual(c.get('/customers/').status_code, 403)
        self.assertEqual(c.get('/invoices/').status_code, 403)

    def test_administrador_accede_a_todo(self):
        c = Client(); c.force_login(self.admin)
        for url in ('/brands/', '/customers/', '/invoices/', '/purchases/'):
            self.assertEqual(c.get(url).status_code, 200, url)
