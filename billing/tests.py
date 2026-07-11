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


class ProductImageUploadTests(TestCase):
    """Regresión del error 500 al guardar un producto con imagen: definir
    STORAGES a mano (para Whitenoise) reemplaza el dict completo de Django,
    y sin la clave 'default' cualquier subida revienta con
    InvalidStorageError. Este test crea un producto con imagen real."""

    @classmethod
    def setUpTestData(cls):
        cls.brand, cls.group, _, _, _ = _make_catalog()
        cls.admin = User.objects.create_superuser('admin_img', 'a@a.com', 'pass12345')

    def test_crear_producto_con_imagen_no_da_500(self):
        import io
        from PIL import Image as PILImage
        buf = io.BytesIO()
        PILImage.new('RGB', (10, 10), 'red').save(buf, format='PNG')
        buf.seek(0)
        buf.name = 'test_upload.png'

        client = Client()
        client.force_login(self.admin)
        r = client.post('/products/create/', {
            'name': 'Producto con imagen', 'brand': self.brand.pk, 'group': self.group.pk,
            'unit_price': '5.00', 'stock': '3', 'is_active': 'on', 'image': buf,
        }, follow=True)
        self.assertEqual(r.status_code, 200)
        product = Product.objects.get(name='Producto con imagen')
        self.assertTrue(product.image.name.startswith('products/'))
        product.image.delete(save=False)  # no dejar el archivo de prueba en media/


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


# =====================================================================
# Portal del Cliente (row-level: solo SUS datos)
# =====================================================================
class CustomerPortalTests(TestCase):
    """El portal /portal/ filtra por el cliente vinculado al usuario, no por
    permisos de modelo. Lo crítico: un cliente JAMÁS ve facturas ajenas."""

    @classmethod
    def setUpTestData(cls):
        call_command('setup_roles')
        cls.brand, cls.group, cls.supplier, cls.product, cls.customer = _make_catalog()
        cls.other_customer = Customer.objects.create(
            dni='0926687856', first_name='Luis', last_name='Mora')

        cliente_group = Group.objects.get(name='Cliente')
        cls.user_ana = User.objects.create_user('ana_portal', password='pass12345')
        cls.user_ana.groups.add(cliente_group)
        cls.customer.user = cls.user_ana
        cls.customer.save(update_fields=['user'])

        # facturas: una de Ana (pendiente) y una del otro cliente
        cls.inv_ana = Invoice.objects.create(customer=cls.customer, total=Decimal('23.00'))
        cls.inv_other = Invoice.objects.create(customer=cls.other_customer, total=Decimal('9.00'))

        cls.vendedor = User.objects.create_user('vend_portal', password='pass12345')
        cls.vendedor.groups.add(Group.objects.get(name='Vendedor'))

    def setUp(self):
        self.client = Client()
        self.client.force_login(self.user_ana)

    def test_mis_facturas_solo_muestra_las_propias(self):
        r = self.client.get('/portal/facturas/')
        self.assertEqual(r.status_code, 200)
        html = r.content.decode()
        self.assertIn(f'/portal/facturas/{self.inv_ana.pk}/', html)
        self.assertNotIn(f'/portal/facturas/{self.inv_other.pk}/', html)

    def test_factura_ajena_da_404(self):
        r = self.client.get(f'/portal/facturas/{self.inv_other.pk}/')
        self.assertEqual(r.status_code, 404)
        r_pdf = self.client.get(f'/portal/facturas/{self.inv_other.pk}/pdf/')
        self.assertEqual(r_pdf.status_code, 404)

    def test_detalle_y_pdf_de_factura_propia(self):
        r = self.client.get(f'/portal/facturas/{self.inv_ana.pk}/')
        self.assertEqual(r.status_code, 200)
        r_pdf = self.client.get(f'/portal/facturas/{self.inv_ana.pk}/pdf/')
        self.assertEqual(r_pdf.status_code, 200)
        self.assertEqual(r_pdf['Content-Type'], 'application/pdf')

    def test_home_redirige_al_portal(self):
        r = self.client.get('/', follow=True)
        self.assertEqual(r.redirect_chain[0][0], '/portal/')

    def test_cliente_no_accede_a_secciones_internas(self):
        for url in ('/products/create/', '/brands/', '/customers/', '/invoices/', '/purchases/'):
            self.assertEqual(self.client.get(url).status_code, 403, url)

    def test_usuario_interno_sin_vinculo_no_entra_al_portal(self):
        c = Client(); c.force_login(self.vendedor)
        r = c.get('/portal/', follow=True)
        self.assertIn('no está vinculado', r.content.decode())

    def test_editar_mis_datos_contacto(self):
        r = self.client.post('/portal/mis-datos/', {
            'email': 'nuevo@example.com', 'phone': '0999999999', 'address': 'Calle Nueva 1',
        }, follow=True)
        self.assertEqual(r.status_code, 200)
        self.customer.refresh_from_db()
        self.assertEqual(self.customer.email, 'nuevo@example.com')
        # identidad intacta (el form no expone estos campos)
        self.assertEqual(self.customer.dni, '1710034065')

    def test_pagar_mi_factura_con_paypal_mockeado(self):
        def fake_post(url, **kwargs):
            class R:
                def __init__(self, data): self._data = data
                def raise_for_status(self): pass
                def json(self): return self._data
            if 'oauth2/token' in url:
                return R({'access_token': 'FAKE'})
            if url.endswith('/v2/checkout/orders'):
                return R({'id': 'ORD-P', 'links': [{'rel': 'approve', 'href': 'https://paypal.test/ok'}]})
            if '/v2/checkout/orders/ORD-P/capture' in url:
                return R({'status': 'COMPLETED',
                          'purchase_units': [{'payments': {'captures': [{'id': 'CAP-P'}]}}]})
            raise AssertionError(url)

        with patch.object(paypal.settings, 'PAYPAL_CLIENT_ID', 'x'), \
             patch.object(paypal.settings, 'PAYPAL_CLIENT_SECRET', 'y'), \
             patch('billing.paypal.requests.post', side_effect=fake_post):
            r1 = self.client.post(f'/portal/facturas/{self.inv_ana.pk}/paypal/start/')
            self.assertEqual(r1.status_code, 302)
            self.assertEqual(r1.url, 'https://paypal.test/ok')
            self.client.get(f'/portal/facturas/{self.inv_ana.pk}/paypal/return/', {'token': 'ORD-P'})

        self.inv_ana.refresh_from_db()
        self.assertEqual(self.inv_ana.payment_status, 'PAGADA')
        self.assertEqual(self.inv_ana.payment_method, 'paypal')
        log = PaymentLog.objects.get(invoice=self.inv_ana)
        self.assertEqual(log.user, self.user_ana)
        self.assertIn('portal cliente', log.note)

    def test_no_puede_pagar_factura_ajena_via_paypal(self):
        with patch.object(paypal.settings, 'PAYPAL_CLIENT_ID', 'x'), \
             patch.object(paypal.settings, 'PAYPAL_CLIENT_SECRET', 'y'):
            r = self.client.post(f'/portal/facturas/{self.inv_other.pk}/paypal/start/')
        self.assertEqual(r.status_code, 404)


class ClienteUserCreationTests(TestCase):
    """El alta de usuarios con rol Cliente exige y aplica el vínculo."""

    @classmethod
    def setUpTestData(cls):
        call_command('setup_roles')
        _, _, _, _, cls.customer = _make_catalog()
        cls.admin = User.objects.create_superuser('admin_uc', 'a@a.com', 'pass12345')

    def _post_user(self, **extra):
        c = Client(); c.force_login(self.admin)
        data = {'username': 'cli_nuevo', 'first_name': 'Ana', 'last_name': 'Torres Vega',
                'email': 'cli@example.com', 'auto_password': 'on',
                'role': Group.objects.get(name='Cliente').pk}
        data.update(extra)
        return c.post('/security/users/create/', data, follow=True)

    def test_rol_cliente_sin_vinculo_es_rechazado(self):
        r = self._post_user()
        self.assertFalse(User.objects.filter(username='cli_nuevo').exists())
        self.assertIn('requiere elegir', r.content.decode())

    def test_rol_cliente_con_vinculo_crea_y_vincula(self):
        self._post_user(customer=self.customer.pk)
        user = User.objects.get(username='cli_nuevo')
        self.customer.refresh_from_db()
        self.assertEqual(self.customer.user, user)
        self.assertTrue(user.groups.filter(name='Cliente').exists())

    def test_vinculo_con_rol_interno_es_rechazado(self):
        r = self._post_user(role=Group.objects.get(name='Vendedor').pk,
                            customer=self.customer.pk)
        self.assertFalse(User.objects.filter(username='cli_nuevo').exists())
        self.assertIn('Solo las cuentas con rol Cliente', r.content.decode())

    def test_form_trae_datos_para_busqueda_y_autollenado(self):
        """El selector muestra 'Apellido, Nombre — cédula — email' (para el
        buscador) y la página incluye el JSON de autollenado."""
        c = Client(); c.force_login(self.admin)
        html = c.get('/security/users/create/').content.decode()
        self.assertIn(f'Torres, Ana — {self.customer.dni}', html)   # label enriquecido
        self.assertIn('"first_name": "Ana"', html)                  # customers_json
        self.assertIn('Buscar por nombre', html)                    # buscador JS


# =====================================================================
# Tienda del portal: catálogo + carrito en sesión + checkout
# =====================================================================
class PortalShopTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command('setup_roles')
        cls.brand, cls.group, cls.supplier, cls.product, cls.customer = _make_catalog()
        # producto extra inactivo: no debe aparecer en el catálogo
        cls.inactive = Product.objects.create(
            name='Producto Oculto', brand=cls.brand, group=cls.group,
            unit_price=Decimal('4.00'), stock=9, is_active=False)

        cls.user = User.objects.create_user('shopper', password='pass12345')
        cls.user.groups.add(Group.objects.get(name='Cliente'))
        cls.customer.user = cls.user
        cls.customer.save(update_fields=['user'])

    def setUp(self):
        self.client = Client()
        self.client.force_login(self.user)

    def test_catalogo_muestra_solo_activos(self):
        r = self.client.get('/portal/')
        self.assertEqual(r.status_code, 200)
        html = r.content.decode()
        self.assertIn('Producto X', html)
        self.assertNotIn('Producto Oculto', html)

    def test_busqueda_del_catalogo(self):
        r = self.client.get('/portal/?q=Marca X')
        self.assertIn('Producto X', r.content.decode())
        r2 = self.client.get('/portal/?q=zzz-no-existe')
        self.assertIn('coincide', r2.content.decode())

    def test_agregar_al_carrito_y_badge(self):
        self.client.post(f'/portal/carrito/agregar/{self.product.pk}/', {'qty': '3'})
        r = self.client.get('/portal/carrito/')
        self.assertContains(r, 'Producto X')
        self.assertEqual(self.client.session['cart'][str(self.product.pk)], 3)

    def test_agregar_mas_que_stock_se_limita(self):
        self.client.post(f'/portal/carrito/agregar/{self.product.pk}/', {'qty': '999'})
        self.assertEqual(self.client.session['cart'][str(self.product.pk)], 20)  # stock

    def test_actualizar_y_quitar_del_carrito(self):
        self.client.post(f'/portal/carrito/agregar/{self.product.pk}/', {'qty': '2'})
        self.client.post(f'/portal/carrito/actualizar/{self.product.pk}/', {'qty': '5'})
        self.assertEqual(self.client.session['cart'][str(self.product.pk)], 5)
        self.client.post(f'/portal/carrito/quitar/{self.product.pk}/')
        self.assertNotIn(str(self.product.pk), self.client.session['cart'])

    def test_checkout_crea_factura_descuenta_stock_y_limpia_carrito(self):
        self.client.post(f'/portal/carrito/agregar/{self.product.pk}/', {'qty': '4'})
        r = self.client.post('/portal/checkout/', follow=True)

        invoice = Invoice.objects.get(customer=self.customer)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 16)                    # 20 - 4
        self.assertEqual(invoice.subtotal, Decimal('40.00'))
        self.assertEqual(invoice.total, Decimal('46.00'))           # + IVA 15%
        self.assertEqual(invoice.payment_status, 'PENDIENTE')
        self.assertIsNotNone(invoice.numero_factura)                # electrónica
        self.assertEqual(len(invoice.clave_acceso), 49)
        self.assertEqual(self.client.session['cart'], {})           # carrito limpio
        # aterriza en el detalle de SU factura (donde está el botón PayPal)
        self.assertEqual(r.redirect_chain[-1][0], f'/portal/facturas/{invoice.pk}/')

    def test_checkout_con_stock_insuficiente_no_compra_nada(self):
        # se agrega al tope del stock y luego el stock baja (compró otro)
        self.client.post(f'/portal/carrito/agregar/{self.product.pk}/', {'qty': '20'})
        Product.objects.filter(pk=self.product.pk).update(stock=2)
        r = self.client.post('/portal/checkout/', follow=True)
        self.assertEqual(Invoice.objects.filter(customer=self.customer).count(), 0)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 2)                     # intacto
        self.assertIn('insuficiente', r.content.decode().lower())
        # el carrito NO se limpia: el cliente puede ajustar cantidades
        self.assertEqual(self.client.session['cart'][str(self.product.pk)], 20)

    def test_checkout_con_carrito_vacio_redirige(self):
        r = self.client.post('/portal/checkout/', follow=True)
        self.assertIn('vacío', r.content.decode())
        self.assertEqual(Invoice.objects.filter(customer=self.customer).count(), 0)

    def test_producto_desactivado_se_retira_del_carrito(self):
        self.client.post(f'/portal/carrito/agregar/{self.product.pk}/', {'qty': '2'})
        Product.objects.filter(pk=self.product.pk).update(is_active=False)
        r = self.client.get('/portal/carrito/')
        self.assertIn('ya no están disponibles', r.content.decode())
        self.assertEqual(self.client.session['cart'], {})

    def test_usuario_interno_no_accede_a_la_tienda(self):
        vendedor = User.objects.create_user('vend_shop', password='pass12345')
        vendedor.groups.add(Group.objects.get(name='Vendedor'))
        c = Client(); c.force_login(vendedor)
        r = c.get('/portal/', follow=True)
        self.assertIn('no está vinculado', r.content.decode())


class InvoiceDeleteTests(TestCase):
    """Una factura a crédito tiene CuotaVenta con on_delete=PROTECT: borrarla
    debe mostrar un mensaje claro, no un 500 (ver creditos_ventas.models)."""
    @classmethod
    def setUpTestData(cls):
        cls.brand, cls.group, cls.supplier, cls.product, cls.customer = _make_catalog()
        cls.admin = User.objects.create_superuser('admin_del', 'a@a.com', 'pass12345')

    def setUp(self):
        self.client = Client()
        self.client.force_login(self.admin)

    def test_eliminar_factura_sin_cuotas_funciona(self):
        invoice = Invoice.objects.create(customer=self.customer, subtotal=Decimal('10'),
                                         tax=Decimal('1.5'), total=Decimal('11.5'))
        r = self.client.post(f'/invoices/{invoice.pk}/delete/', follow=True)
        self.assertEqual(r.status_code, 200)
        self.assertFalse(Invoice.objects.filter(pk=invoice.pk).exists())

    def test_eliminar_factura_con_cuotas_no_revienta_y_avisa(self):
        from creditos_ventas.services import generar_cuotas_venta
        invoice = Invoice.objects.create(customer=self.customer, subtotal=Decimal('20'),
                                         tax=Decimal('3'), total=Decimal('23'))
        generar_cuotas_venta(invoice, 3)
        r = self.client.post(f'/invoices/{invoice.pk}/delete/', follow=True)
        self.assertEqual(r.status_code, 200)
        self.assertTrue(Invoice.objects.filter(pk=invoice.pk).exists())  # no se borró
        self.assertIn('plan de cuotas', r.content.decode().lower())
