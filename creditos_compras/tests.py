"""Suite de tests de creditos_compras: generación de cuotas de compra,
registro de pagos (validaciones), tipo de pago al crear la compra,
comprobante PDF y permisos.

Corre con: python manage.py test creditos_compras
"""
from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth.models import Group, User
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.db.models import ProtectedError
from django.test import Client, TestCase

from purchasing.models import Purchase
from purchasing.tests import _make_catalog as _make_purchase_catalog

from .models import CuotaCompra
from .receipts import build_pago_cuota_compra_pdf_bytes
from .services import generar_cuotas_compra, registrar_pagos_compra


# =====================================================================
# Generación de cuotas
# =====================================================================
class GenerarCuotasCompraTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        _, _, cls.supplier, _ = _make_purchase_catalog()

    def test_suma_exacta_al_total_no_divisible(self):
        purchase = Purchase.objects.create(supplier=self.supplier, document_number='CR-1', total=Decimal('100.00'))
        cuotas = generar_cuotas_compra(purchase, 3)
        self.assertEqual(sum(c.valor for c in cuotas), Decimal('100.00'))
        self.assertEqual([c.valor for c in cuotas],
                         [Decimal('33.33'), Decimal('33.33'), Decimal('33.34')])

    def test_generar_actualiza_saldo_y_estado_de_la_compra(self):
        purchase = Purchase.objects.create(supplier=self.supplier, document_number='CR-2', total=Decimal('60.00'))
        generar_cuotas_compra(purchase, 3)
        purchase.refresh_from_db()
        self.assertEqual(purchase.saldo, Decimal('60.00'))
        self.assertEqual(purchase.estado, 'PENDIENTE')
        self.assertEqual(purchase.tipo_pago, 'CREDITO')

    def test_num_cuotas_menor_a_uno_rechazado(self):
        purchase = Purchase.objects.create(supplier=self.supplier, document_number='CR-0', total=Decimal('50.00'))
        with self.assertRaises(ValidationError):
            generar_cuotas_compra(purchase, 0)
        self.assertEqual(CuotaCompra.objects.filter(compra=purchase).count(), 0)

    def test_no_generar_cuotas_sobre_compra_ya_pagada(self):
        purchase = Purchase.objects.create(supplier=self.supplier, document_number='CR-3',
                                           total=Decimal('40.00'), estado='PAGADA')
        with self.assertRaises(ValidationError):
            generar_cuotas_compra(purchase, 2)

    def test_no_generar_dos_planes_sobre_la_misma_compra(self):
        purchase = Purchase.objects.create(supplier=self.supplier, document_number='CR-4', total=Decimal('80.00'))
        generar_cuotas_compra(purchase, 2)
        with self.assertRaises(ValidationError):
            generar_cuotas_compra(purchase, 3)


# =====================================================================
# Registro de pagos
# =====================================================================
class RegistrarPagosCompraTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        _, _, cls.supplier, _ = _make_purchase_catalog()

    def setUp(self):
        self.purchase = Purchase.objects.create(supplier=self.supplier, document_number='CR-P1',
                                                total=Decimal('200.00'))
        self.cuotas = generar_cuotas_compra(self.purchase, 2)  # 100, 100

    def test_pago_parcial_actualiza_saldo_sin_marcar_pagada(self):
        cuota = self.cuotas[0]
        registrar_pagos_compra([(cuota, Decimal('40.00'))], date.today())
        cuota.refresh_from_db()
        self.assertEqual(cuota.saldo, Decimal('60.00'))
        self.assertEqual(cuota.estado, 'PENDIENTE')

    def test_pagar_todas_las_cuotas_marca_la_compra_pagada(self):
        registrar_pagos_compra([(c, c.saldo) for c in self.cuotas], date.today())
        self.purchase.refresh_from_db()
        self.assertEqual(self.purchase.saldo, Decimal('0.00'))
        self.assertEqual(self.purchase.estado, 'PAGADA')

    def test_pago_mayor_al_saldo_rechazado(self):
        with self.assertRaises(ValidationError):
            registrar_pagos_compra([(self.cuotas[0], Decimal('999.00'))], date.today())

    def test_pago_cero_o_negativo_rechazado(self):
        with self.assertRaises(ValidationError):
            registrar_pagos_compra([(self.cuotas[0], Decimal('0'))], date.today())
        with self.assertRaises(ValidationError):
            registrar_pagos_compra([(self.cuotas[0], Decimal('-10'))], date.today())

    def test_fecha_de_pago_futura_rechazada(self):
        with self.assertRaises(ValidationError):
            registrar_pagos_compra([(self.cuotas[0], Decimal('50'))], date.today() + timedelta(days=1))

    def test_no_pagar_cuotas_de_una_compra_ya_pagada(self):
        self.purchase.estado = 'PAGADA'
        self.purchase.save(update_fields=['estado'])
        with self.assertRaises(ValidationError):
            registrar_pagos_compra([(self.cuotas[0], Decimal('50.00'))], date.today())

    def test_no_se_puede_eliminar_una_cuota_con_pagos_registrados(self):
        cuota = self.cuotas[0]
        registrar_pagos_compra([(cuota, Decimal('50.00'))], date.today())
        with self.assertRaises(ProtectedError):
            cuota.delete()


# =====================================================================
# Vista: registro del tipo de pago al crear la compra
# =====================================================================
class PurchaseCreateTipoPagoTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.brand, cls.group, cls.supplier, cls.product = _make_purchase_catalog()
        cls.admin = User.objects.create_superuser('admin_pp', 'a@a.com', 'pass12345')

    def setUp(self):
        self.client = Client()
        self.client.force_login(self.admin)

    def _post(self, document, extra=None):
        data = {
            'supplier': self.supplier.pk, 'document_number': document,
            'details-TOTAL_FORMS': '1', 'details-INITIAL_FORMS': '0',
            'details-MIN_NUM_FORMS': '0', 'details-MAX_NUM_FORMS': '1000',
            'details-0-product': self.product.pk, 'details-0-quantity': '2', 'details-0-unit_cost': '10.00',
        }
        data.update(extra or {})
        return self.client.post('/purchases/create/', data, follow=True)

    def test_sin_tipo_pago_en_el_post_usa_contado_por_defecto(self):
        self._post('PP-1')
        purchase = Purchase.objects.latest('id')
        self.assertEqual(purchase.tipo_pago, 'CONTADO')
        self.assertEqual(purchase.estado, 'PAGADA')
        self.assertEqual(purchase.saldo, Decimal('0.00'))

    def test_credito_genera_las_cuotas_solicitadas(self):
        self._post('PP-2', {'tipo_pago': 'CREDITO', 'num_cuotas': '5'})
        purchase = Purchase.objects.latest('id')
        self.assertEqual(purchase.tipo_pago, 'CREDITO')
        self.assertEqual(CuotaCompra.objects.filter(compra=purchase).count(), 5)

    def test_credito_sin_num_cuotas_rechaza_el_formulario(self):
        before = Purchase.objects.count()
        r = self._post('PP-3', {'tipo_pago': 'CREDITO', 'num_cuotas': ''})
        self.assertEqual(Purchase.objects.count(), before)
        self.assertIn('cuotas mensuales', r.content.decode().lower())


# =====================================================================
# Vista: registrar pago (formset) de punta a punta + comprobante PDF
# =====================================================================
class PagarCuotasCompraViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        _, _, cls.supplier, _ = _make_purchase_catalog()
        cls.admin = User.objects.create_superuser('admin_pcc', 'a@a.com', 'pass12345')

    def setUp(self):
        self.client = Client()
        self.client.force_login(self.admin)
        self.purchase = Purchase.objects.create(supplier=self.supplier, document_number='CR-V1',
                                                total=Decimal('200.00'))
        self.cuotas = generar_cuotas_compra(self.purchase, 2)  # 100, 100

    def test_pagar_una_cuota_desde_la_vista(self):
        data = {
            'fecha': date.today().isoformat(), 'observacion': 'Transferencia al proveedor',
            'form-TOTAL_FORMS': '2', 'form-INITIAL_FORMS': '0',
            'form-MIN_NUM_FORMS': '0', 'form-MAX_NUM_FORMS': '1000',
            'form-0-cuota_id': str(self.cuotas[0].pk), 'form-0-pagar': 'on', 'form-0-monto': '100.00',
            'form-1-cuota_id': str(self.cuotas[1].pk), 'form-1-pagar': '', 'form-1-monto': '',
        }
        self.client.post(f'/creditos/compras/compra/{self.purchase.pk}/pagar/', data, follow=True)
        self.cuotas[0].refresh_from_db()
        self.purchase.refresh_from_db()
        self.assertEqual(self.cuotas[0].estado, 'PAGADA')
        self.assertEqual(self.purchase.saldo, Decimal('100.00'))

    def test_comprobante_pdf_del_pago(self):
        registrar_pagos_compra([(self.cuotas[0], Decimal('100.00'))], date.today())
        pago = self.cuotas[0].pagos.first()
        pdf = build_pago_cuota_compra_pdf_bytes(pago)
        self.assertTrue(pdf.startswith(b'%PDF'))
        r = self.client.get(f'/creditos/compras/pago/{pago.pk}/pdf/')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r['Content-Type'], 'application/pdf')


# =====================================================================
# Permisos
# =====================================================================
class CreditosComprasPermissionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command('setup_roles')
        _, _, cls.supplier, _ = _make_purchase_catalog()
        cls.vendedor = User.objects.create_user('vendedor_cc', password='pass12345')
        cls.vendedor.groups.add(Group.objects.get(name='Vendedor'))
        cls.comprador = User.objects.create_user('comprador_cc', password='pass12345')
        cls.comprador.groups.add(Group.objects.get(name='Analista de Compras'))

        cls.purchase = Purchase.objects.create(supplier=cls.supplier, document_number='PERM-1',
                                               total=Decimal('50.00'))
        generar_cuotas_compra(cls.purchase, 2)

    def test_analista_compras_accede_a_cuotas_de_compra(self):
        c = Client(); c.force_login(self.comprador)
        self.assertEqual(c.get('/creditos/compras/pendientes/').status_code, 200)
        self.assertEqual(c.get(f'/creditos/compras/compra/{self.purchase.pk}/').status_code, 200)

    def test_vendedor_no_accede_a_cuotas_de_compra(self):
        c = Client(); c.force_login(self.vendedor)
        self.assertEqual(c.get('/creditos/compras/pendientes/').status_code, 403)
