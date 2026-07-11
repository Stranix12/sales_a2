"""Suite de tests de creditos_ventas: generación de cuotas de venta,
registro de pagos (validaciones), sincronización de saldo/estado de la
factura y permisos. El crédito de compras se prueba en creditos_compras.

Corre con: python manage.py test creditos_ventas
"""
from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth.models import Group, User
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.db.models import ProtectedError
from django.test import Client, TestCase

from billing.models import Invoice, PaymentLog
from billing.tests import _make_catalog

from .models import CuotaVenta
from .services import generar_cuotas_venta, registrar_pagos_venta


# =====================================================================
# Generación de cuotas — venta
# =====================================================================
class GenerarCuotasVentaTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        _, _, _, _, cls.customer = _make_catalog()

    def test_suma_exacta_al_total_no_divisible(self):
        invoice = Invoice.objects.create(customer=self.customer, total=Decimal('100.00'))
        cuotas = generar_cuotas_venta(invoice, 3)
        self.assertEqual(sum(c.valor for c in cuotas), Decimal('100.00'))
        self.assertEqual([c.valor for c in cuotas],
                         [Decimal('33.33'), Decimal('33.33'), Decimal('33.34')])

    def test_cuota_unica_igual_al_total(self):
        invoice = Invoice.objects.create(customer=self.customer, total=Decimal('55.55'))
        cuotas = generar_cuotas_venta(invoice, 1)
        self.assertEqual(len(cuotas), 1)
        self.assertEqual(cuotas[0].valor, Decimal('55.55'))
        self.assertEqual(cuotas[0].saldo, Decimal('55.55'))

    def test_fechas_vencimiento_mensuales_consecutivas(self):
        invoice = Invoice.objects.create(customer=self.customer, total=Decimal('90.00'))
        cuotas = generar_cuotas_venta(invoice, 3)
        base_y, base_m = invoice.invoice_date.year, invoice.invoice_date.month
        esperado = []
        y, m = base_y, base_m
        for _ in range(3):
            m += 1
            if m > 12:
                m = 1
                y += 1
            esperado.append((y, m))
        obtenido = [(c.fecha_vencimiento.year, c.fecha_vencimiento.month) for c in cuotas]
        self.assertEqual(obtenido, esperado)

    def test_generar_actualiza_saldo_y_estado_de_la_factura(self):
        invoice = Invoice.objects.create(customer=self.customer, total=Decimal('100.00'))
        generar_cuotas_venta(invoice, 4)
        invoice.refresh_from_db()
        self.assertEqual(invoice.saldo, Decimal('100.00'))
        self.assertEqual(invoice.estado, 'PENDIENTE')
        self.assertEqual(invoice.tipo_pago, 'CREDITO')

    def test_num_cuotas_menor_a_uno_rechazado(self):
        invoice = Invoice.objects.create(customer=self.customer, total=Decimal('100.00'))
        with self.assertRaises(ValidationError):
            generar_cuotas_venta(invoice, 0)
        self.assertEqual(CuotaVenta.objects.filter(factura=invoice).count(), 0)

    def test_no_generar_cuotas_sobre_factura_ya_pagada(self):
        invoice = Invoice.objects.create(customer=self.customer, total=Decimal('100.00'), estado='PAGADA')
        with self.assertRaises(ValidationError):
            generar_cuotas_venta(invoice, 3)

    def test_no_generar_dos_planes_sobre_la_misma_factura(self):
        invoice = Invoice.objects.create(customer=self.customer, total=Decimal('100.00'))
        generar_cuotas_venta(invoice, 2)
        with self.assertRaises(ValidationError):
            generar_cuotas_venta(invoice, 3)


# =====================================================================
# Registro de pagos — venta
# =====================================================================
class RegistrarPagosVentaTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        _, _, _, _, cls.customer = _make_catalog()
        cls.admin = User.objects.create_superuser('admin_cred', 'a@a.com', 'pass12345')

    def setUp(self):
        self.invoice = Invoice.objects.create(customer=self.customer, total=Decimal('300.00'))
        self.cuotas = generar_cuotas_venta(self.invoice, 3)  # 100, 100, 100

    def test_pago_parcial_actualiza_saldo_sin_marcar_pagada(self):
        cuota = self.cuotas[0]
        registrar_pagos_venta([(cuota, Decimal('40.00'))], date.today())
        cuota.refresh_from_db()
        self.assertEqual(cuota.saldo, Decimal('60.00'))
        self.assertEqual(cuota.estado, 'PENDIENTE')

    def test_pago_completo_marca_la_cuota_pagada(self):
        cuota = self.cuotas[0]
        registrar_pagos_venta([(cuota, Decimal('100.00'))], date.today())
        cuota.refresh_from_db()
        self.assertEqual(cuota.saldo, Decimal('0.00'))
        self.assertEqual(cuota.estado, 'PAGADA')

    def test_pago_de_varias_cuotas_en_un_solo_envio(self):
        registrar_pagos_venta(
            [(self.cuotas[0], Decimal('100.00')), (self.cuotas[1], Decimal('50.00'))],
            date.today(),
        )
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.saldo, Decimal('150.00'))  # 0 + 50 + 100

    def test_pago_mayor_al_saldo_de_la_cuota_rechazado(self):
        with self.assertRaises(ValidationError):
            registrar_pagos_venta([(self.cuotas[0], Decimal('150.00'))], date.today())
        self.cuotas[0].refresh_from_db()
        self.assertEqual(self.cuotas[0].saldo, Decimal('100.00'))  # sin cambios (todo o nada)

    def test_pago_cero_rechazado(self):
        with self.assertRaises(ValidationError):
            registrar_pagos_venta([(self.cuotas[0], Decimal('0'))], date.today())

    def test_pago_negativo_rechazado(self):
        with self.assertRaises(ValidationError):
            registrar_pagos_venta([(self.cuotas[0], Decimal('-10'))], date.today())

    def test_sin_cuotas_seleccionadas_rechazado(self):
        with self.assertRaises(ValidationError):
            registrar_pagos_venta([], date.today())

    def test_fecha_de_pago_futura_rechazada(self):
        with self.assertRaises(ValidationError):
            registrar_pagos_venta([(self.cuotas[0], Decimal('50'))], date.today() + timedelta(days=1))

    def test_fecha_de_pago_anterior_a_la_factura_rechazada(self):
        with self.assertRaises(ValidationError):
            registrar_pagos_venta(
                [(self.cuotas[0], Decimal('50'))],
                self.invoice.invoice_date.date() - timedelta(days=1),
            )

    def test_pagar_todas_las_cuotas_marca_la_factura_pagada_y_crea_paymentlog(self):
        registrar_pagos_venta([(c, c.saldo) for c in self.cuotas], date.today(), user=self.admin)
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.saldo, Decimal('0.00'))
        self.assertEqual(self.invoice.estado, 'PAGADA')
        self.assertEqual(self.invoice.payment_status, 'PAGADA')
        self.assertTrue(PaymentLog.objects.filter(invoice=self.invoice, method='credito').exists())

    def test_no_pagar_cuotas_de_un_documento_ya_pagado(self):
        self.invoice.estado = 'PAGADA'
        self.invoice.save(update_fields=['estado'])
        with self.assertRaises(ValidationError):
            registrar_pagos_venta([(self.cuotas[0], Decimal('50.00'))], date.today())

    def test_no_se_puede_eliminar_una_cuota_con_pagos_registrados(self):
        cuota = self.cuotas[0]
        registrar_pagos_venta([(cuota, Decimal('50.00'))], date.today())
        with self.assertRaises(ProtectedError):
            cuota.delete()


# =====================================================================
# Vista: registro del tipo de pago al crear la factura
# =====================================================================
class InvoiceCreateTipoPagoTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.brand, cls.group, cls.supplier, cls.product, cls.customer = _make_catalog()
        cls.admin = User.objects.create_superuser('admin_ip', 'a@a.com', 'pass12345')

    def setUp(self):
        self.client = Client()
        self.client.force_login(self.admin)

    def _post(self, extra=None):
        data = {
            'customer': self.customer.pk,
            'details-TOTAL_FORMS': '1', 'details-INITIAL_FORMS': '0',
            'details-MIN_NUM_FORMS': '0', 'details-MAX_NUM_FORMS': '1000',
            'details-0-product': self.product.pk, 'details-0-quantity': '2', 'details-0-unit_price': '10.00',
        }
        data.update(extra or {})
        return self.client.post('/invoices/create/', data, follow=True)

    def test_sin_tipo_pago_en_el_post_usa_contado_por_defecto(self):
        # Compatibilidad: formularios/tests antiguos que no envían tipo_pago.
        self._post()
        invoice = Invoice.objects.latest('id')
        self.assertEqual(invoice.tipo_pago, 'CONTADO')
        self.assertEqual(invoice.estado, 'PAGADA')
        self.assertEqual(invoice.payment_status, 'PAGADA')
        self.assertEqual(invoice.saldo, Decimal('0.00'))
        self.assertEqual(CuotaVenta.objects.filter(factura=invoice).count(), 0)

    def test_credito_genera_las_cuotas_solicitadas(self):
        self._post({'tipo_pago': 'CREDITO', 'num_cuotas': '4'})
        invoice = Invoice.objects.latest('id')
        self.assertEqual(invoice.tipo_pago, 'CREDITO')
        self.assertEqual(invoice.estado, 'PENDIENTE')
        self.assertEqual(invoice.saldo, invoice.total)
        self.assertEqual(CuotaVenta.objects.filter(factura=invoice).count(), 4)

    def test_credito_sin_num_cuotas_rechaza_el_formulario(self):
        before = Invoice.objects.count()
        r = self._post({'tipo_pago': 'CREDITO', 'num_cuotas': ''})
        self.assertEqual(Invoice.objects.count(), before)
        self.assertIn('cuotas mensuales', r.content.decode().lower())


# =====================================================================
# Vista: registrar pago (formset) de punta a punta
# =====================================================================
class PagarCuotasViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.brand, cls.group, cls.supplier, cls.product, cls.customer = _make_catalog()
        cls.admin = User.objects.create_superuser('admin_pcv', 'a@a.com', 'pass12345')

    def setUp(self):
        self.client = Client()
        self.client.force_login(self.admin)
        self.invoice = Invoice.objects.create(customer=self.customer, total=Decimal('200.00'))
        self.cuotas = generar_cuotas_venta(self.invoice, 2)  # 100, 100

    def test_pagar_una_cuota_desde_la_vista(self):
        data = {
            'fecha': date.today().isoformat(), 'observacion': 'Pago mostrador',
            'form-TOTAL_FORMS': '2', 'form-INITIAL_FORMS': '0',
            'form-MIN_NUM_FORMS': '0', 'form-MAX_NUM_FORMS': '1000',
            'form-0-cuota_id': str(self.cuotas[0].pk), 'form-0-pagar': 'on', 'form-0-monto': '100.00',
            'form-1-cuota_id': str(self.cuotas[1].pk), 'form-1-pagar': '', 'form-1-monto': '',
        }
        self.client.post(f'/creditos/ventas/factura/{self.invoice.pk}/pagar/', data, follow=True)
        self.cuotas[0].refresh_from_db()
        self.invoice.refresh_from_db()
        self.assertEqual(self.cuotas[0].estado, 'PAGADA')
        self.assertEqual(self.invoice.saldo, Decimal('100.00'))


# =====================================================================
# Permisos
# =====================================================================
class CreditosVentasPermissionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command('setup_roles')
        cls.brand, cls.group, cls.supplier, cls.product, cls.customer = _make_catalog()
        cls.vendedor = User.objects.create_user('vendedor_cred', password='pass12345')
        cls.vendedor.groups.add(Group.objects.get(name='Vendedor'))
        cls.comprador = User.objects.create_user('comprador_cred', password='pass12345')
        cls.comprador.groups.add(Group.objects.get(name='Analista de Compras'))

        cls.invoice = Invoice.objects.create(customer=cls.customer, total=Decimal('100.00'))
        generar_cuotas_venta(cls.invoice, 2)

    def test_vendedor_accede_a_cuotas_de_venta(self):
        c = Client(); c.force_login(self.vendedor)
        self.assertEqual(c.get('/creditos/ventas/pendientes/').status_code, 200)
        self.assertEqual(c.get(f'/creditos/ventas/factura/{self.invoice.pk}/').status_code, 200)

    def test_analista_compras_no_accede_a_cuotas_de_venta(self):
        c = Client(); c.force_login(self.comprador)
        self.assertEqual(c.get('/creditos/ventas/pendientes/').status_code, 403)
