"""Suite de tests de purchasing: creación de compras (reabastece stock),
la restricción de no repetir N.º de factura por proveedor, y permisos.

Corre con: python manage.py test purchasing
"""
from decimal import Decimal

from django.contrib.auth.models import Group, User
from django.core.management import call_command
from django.db import IntegrityError, transaction
from django.test import Client, TestCase

from billing.models import Brand, Product, ProductGroup, Supplier
from .models import Purchase, PurchaseDetail


def _make_catalog():
    brand = Brand.objects.create(name='Marca X')
    group = ProductGroup.objects.create(name='Grupo X')
    supplier = Supplier.objects.create(name='Proveedor X')
    product = Product.objects.create(
        name='Producto X', brand=brand, group=group,
        unit_price=Decimal('10.00'), stock=5, is_active=True,
    )
    return brand, group, supplier, product


class PurchaseCreateViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.brand, cls.group, cls.supplier, cls.product = _make_catalog()
        cls.admin = User.objects.create_superuser('admin_p1', 'a@a.com', 'pass12345')

    def setUp(self):
        self.client = Client()
        self.client.force_login(self.admin)

    def _post(self, lines, document='F-100'):
        data = {
            'supplier': self.supplier.pk, 'document_number': document,
            'details-TOTAL_FORMS': str(len(lines)), 'details-INITIAL_FORMS': '0',
            'details-MIN_NUM_FORMS': '0', 'details-MAX_NUM_FORMS': '1000',
        }
        for i, (product, qty, cost) in enumerate(lines):
            data[f'details-{i}-product'] = product.pk if product else ''
            data[f'details-{i}-quantity'] = qty
            data[f'details-{i}-unit_cost'] = cost
        return self.client.post('/purchases/create/', data, follow=True)

    def test_creacion_normal_reabastece_stock(self):
        self._post([(self.product, '10', '6.00')])
        purchase = Purchase.objects.latest('id')
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 15)  # 5 + 10
        self.assertEqual(purchase.total, Decimal('69.00'))  # 60 + 15% IVA

    def test_documento_duplicado_mismo_proveedor_es_rechazado(self):
        self._post([(self.product, '5', '6.00')], document='DUP-1')
        before = Purchase.objects.count()
        self._post([(self.product, '5', '6.00')], document='DUP-1')
        self.assertEqual(Purchase.objects.count(), before)  # la 2da no se crea


class PurchaseConstraintTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.brand, cls.group, cls.supplier, cls.product = _make_catalog()

    def test_unique_together_supplier_document_number(self):
        Purchase.objects.create(supplier=self.supplier, document_number='X-1')
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Purchase.objects.create(supplier=self.supplier, document_number='X-1')

    def test_mismo_documento_distinto_proveedor_si_se_permite(self):
        other_supplier = Supplier.objects.create(name='Otro Proveedor')
        Purchase.objects.create(supplier=self.supplier, document_number='X-2')
        Purchase.objects.create(supplier=other_supplier, document_number='X-2')  # no debe lanzar
        self.assertEqual(Purchase.objects.filter(document_number='X-2').count(), 2)


class PurchasePermissionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command('setup_roles')
        cls.brand, cls.group, cls.supplier, cls.product = _make_catalog()
        cls.comprador = User.objects.create_user('comprador_p', password='pass12345')
        cls.comprador.groups.add(Group.objects.get(name='Analista de Compras'))
        cls.vendedor = User.objects.create_user('vendedor_p', password='pass12345')
        cls.vendedor.groups.add(Group.objects.get(name='Vendedor'))

    def test_analista_compras_puede_ver_y_crear(self):
        c = Client(); c.force_login(self.comprador)
        self.assertEqual(c.get('/purchases/').status_code, 200)
        self.assertEqual(c.get('/purchases/create/').status_code, 200)

    def test_vendedor_no_puede_acceder_a_compras(self):
        c = Client(); c.force_login(self.vendedor)
        self.assertEqual(c.get('/purchases/').status_code, 403)
        self.assertEqual(c.get('/purchases/create/').status_code, 403)

    def test_vendedor_no_puede_eliminar_compra(self):
        purchase = Purchase.objects.create(supplier=self.supplier, document_number='DEL-1')
        c = Client(); c.force_login(self.vendedor)
        self.assertEqual(c.get(f'/purchases/{purchase.pk}/delete/').status_code, 403)


class PurchaseDeleteTests(TestCase):
    """Una compra a crédito tiene CuotaCompra con on_delete=PROTECT: borrarla
    debe mostrar un mensaje claro, no un 500 (ver creditos_compras.models)."""
    @classmethod
    def setUpTestData(cls):
        cls.brand, cls.group, cls.supplier, cls.product = _make_catalog()
        cls.admin = User.objects.create_superuser('admin_pdel', 'a@a.com', 'pass12345')

    def setUp(self):
        self.client = Client()
        self.client.force_login(self.admin)

    def test_eliminar_compra_con_cuotas_no_revienta_y_avisa(self):
        from creditos_compras.services import generar_cuotas_compra
        purchase = Purchase.objects.create(supplier=self.supplier, document_number='DEL-CR-1',
                                           total=Decimal('60.00'))
        generar_cuotas_compra(purchase, 3)
        r = self.client.post(f'/purchases/{purchase.pk}/delete/', follow=True)
        self.assertEqual(r.status_code, 200)
        self.assertTrue(Purchase.objects.filter(pk=purchase.pk).exists())  # no se borró
        self.assertIn('plan de cuotas', r.content.decode().lower())
