import random
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import F
from django.db.models.functions import Greatest
from django.utils import timezone

from billing.electronic import asignar_datos_electronicos
from billing.models import (
    Brand, Customer, Invoice, InvoiceDetail, PaymentLog, Product,
    ProductGroup, Supplier,
)
from purchasing.models import Purchase, PurchaseDetail

DEMO_EMAIL_DOMAIN = 'demo.local'
PAYMENT_METHODS = ['efectivo', 'transferencia', 'tarjeta']

# Productos con stock deliberadamente bajo/agotado para alimentar el widget
# "Stock bajo" del dashboard; se excluyen de ventas y compras para que ese
# valor no cambie entre corridas.
RESERVED_LOW_STOCK = {'Nesquik 400g', 'Yogurt Toni 1L', 'Chocolate Nestlé Crunch'}

BRANDS = ['Nestlé', 'Coca-Cola', 'Unilever', 'Procter & Gamble', 'La Fabril', 'Pronaca']
GROUPS = ['Bebidas', 'Lácteos', 'Snacks', 'Limpieza', 'Cuidado Personal']

SUPPLIERS = [
    ('Distribuidora Andina S.A.', 'Carlos Ruiz', 'ventas@andina.ec', '022345678'),
    ('Comercial Quito Cía. Ltda.', 'María Salazar', 'contacto@comquito.ec', '023456789'),
    ('Importadora del Pacífico', 'Jorge Vélez', 'info@pacifico.ec', '042345678'),
    ('Mayorista Sierra Norte', 'Lucía Andrade', 'ventas@sierranorte.ec', '062345678'),
]

# (nombre, marca, grupo, precio, stock inicial, activo)
PRODUCTS = [
    ('Coca-Cola 500ml', 'Coca-Cola', 'Bebidas', '0.75', 120, True),
    ('Coca-Cola 1L', 'Coca-Cola', 'Bebidas', '1.25', 80, True),
    ('Nescafé Clásico 170g', 'Nestlé', 'Bebidas', '4.50', 40, True),
    ('Nesquik 400g', 'Nestlé', 'Bebidas', '3.20', 4, True),
    ('Leche La Lechera 400g', 'Nestlé', 'Lácteos', '1.80', 60, True),
    ('Yogurt Toni 1L', 'Pronaca', 'Lácteos', '2.10', 3, True),
    ('Queso Fresco Pronaca 500g', 'Pronaca', 'Lácteos', '3.75', 25, True),
    ('Embutidos Plumrose 250g', 'Pronaca', 'Lácteos', '2.90', 30, True),
    ('Papas Fritas Ruffles 150g', 'Pronaca', 'Snacks', '1.10', 90, True),
    ('Doritos 150g', 'Pronaca', 'Snacks', '1.15', 70, True),
    ('Galletas Oreo 300g', 'Nestlé', 'Snacks', '2.30', 45, True),
    ('Chocolate Nestlé Crunch', 'Nestlé', 'Snacks', '1.50', 0, True),
    ('Detergente Deja 1kg', 'Unilever', 'Limpieza', '3.60', 55, True),
    ('Jabón Ariel 1kg', 'Procter & Gamble', 'Limpieza', '4.10', 38, True),
    ('Cloro Klorox 1L', 'La Fabril', 'Limpieza', '1.40', 65, True),
    ('Shampoo Sedal 400ml', 'Unilever', 'Cuidado Personal', '3.90', 42, True),
    ('Pasta Dental Colgate 100ml', 'Procter & Gamble', 'Cuidado Personal', '2.20', 50, True),
    ('Desodorante Rexona', 'Unilever', 'Cuidado Personal', '3.30', 5, False),
    ('Jabón de Tocador Dove', 'Unilever', 'Cuidado Personal', '1.60', 0, False),
]

# (nombre, apellido, dirección, código de provincia para la cédula)
CUSTOMERS = [
    ('Juan Carlos', 'Torres', 'Av. Amazonas N34-12, Quito', 17),
    ('María José', 'Vásquez', 'Cdla. Kennedy, Guayaquil', 9),
    ('Pedro Andrés', 'Salazar', 'Calle Larga 4-56, Cuenca', 1),
    ('Ana Lucía', 'Ramírez', 'Av. 6 de Diciembre N24-30, Quito', 17),
    ('Diego Fernando', 'Chávez', 'Urdesa Central, Guayaquil', 9),
    ('Gabriela Estefanía', 'Morales', 'Sector Totoracocha, Cuenca', 1),
    ('Luis Miguel', 'Herrera', 'Av. República E7-20, Quito', 17),
    ('Carla Patricia', 'Jiménez', 'Alborada 3ra Etapa, Guayaquil', 9),
    ('Andrés Sebastián', 'Paredes', 'Av. Ordóñez Lasso, Cuenca', 1),
    ('Daniela Alejandra', 'Cevallos', 'La Carolina, Quito', 17),
]


def _cedula(provincia, seq):
    """Cédula ecuatoriana válida (10 dígitos), determinística: mismo par
    (provincia, seq) siempre produce la misma cédula. Tercer dígito fijo en
    0 (persona natural); dígito verificador con el algoritmo módulo 10."""
    base = f'{provincia:02d}0{seq:06d}'
    coef = [2, 1, 2, 1, 2, 1, 2, 1, 2]
    total = 0
    for i, d in enumerate(base):
        r = int(d) * coef[i]
        total += r - 9 if r > 9 else r
    verifier = 10 - (total % 10)
    return base + str(0 if verifier == 10 else verifier)


class Command(BaseCommand):
    help = ('Genera datos de prueba realistas (marcas, grupos, proveedores, productos, '
            'clientes, facturas y compras repartidas en los últimos N meses) para que el '
            'dashboard y las gráficas tengan contenido. El catálogo es idempotente '
            '(get_or_create); las facturas/compras se limitan a un tope por corrida para '
            'no duplicar todo si el comando se ejecuta más de una vez.')

    def add_arguments(self, parser):
        parser.add_argument('--months', type=int, default=6,
                            help='Meses hacia atrás a repartir facturas/compras (default 6).')

    def handle(self, *args, **options):
        months = options['months']
        admin = User.objects.filter(is_superuser=True).first()
        if not admin:
            self.stderr.write(self.style.ERROR(
                'No hay ningún superusuario todavía. Crea uno primero con createsuperuser.'))
            return

        with transaction.atomic():
            brands = self._seed_brands()
            groups = self._seed_groups()
            suppliers = self._seed_suppliers()
            products = self._seed_products(brands, groups, suppliers)
            customers = self._seed_customers()
            n_inv = self._seed_invoices(customers, products, admin, months)
            n_pur = self._seed_purchases(suppliers, products, months)

        self.stdout.write(self.style.SUCCESS(
            f'Listo: {len(brands)} marcas, {len(groups)} grupos, {len(suppliers)} proveedores, '
            f'{len(products)} productos, {len(customers)} clientes, '
            f'{n_inv} facturas nuevas, {n_pur} compras nuevas.'))

    # --- Catálogo (idempotente vía get_or_create: correr 2 veces no duplica) ---

    def _seed_brands(self):
        return [Brand.objects.get_or_create(name=n)[0] for n in BRANDS]

    def _seed_groups(self):
        return [ProductGroup.objects.get_or_create(name=n)[0] for n in GROUPS]

    def _seed_suppliers(self):
        out = []
        for name, contact, email, phone in SUPPLIERS:
            sup, _ = Supplier.objects.get_or_create(
                name=name, defaults={'contact_name': contact, 'email': email, 'phone': phone})
            out.append(sup)
        return out

    def _seed_products(self, brands, groups, suppliers):
        brand_map = {b.name: b for b in brands}
        group_map = {g.name: g for g in groups}
        out = []
        for i, (name, brand_name, group_name, price, stock, active) in enumerate(PRODUCTS):
            prod, created = Product.objects.get_or_create(
                name=name,
                defaults={
                    'brand': brand_map[brand_name], 'group': group_map[group_name],
                    'unit_price': Decimal(price), 'stock': stock, 'is_active': active,
                },
            )
            if created:
                prod.suppliers.add(suppliers[i % len(suppliers)])
            out.append(prod)
        return out

    def _seed_customers(self):
        out = []
        for i, (first, last, address, provincia) in enumerate(CUSTOMERS, start=1):
            dni = _cedula(provincia, i)
            slug = f'{first.split()[0]}.{last.split()[0]}'.lower()
            cust, _ = Customer.objects.get_or_create(
                dni=dni,
                defaults={
                    'first_name': first, 'last_name': last, 'address': address,
                    'phone': f'09{random.randint(10000000, 99999999)}',
                    'email': f'{slug}@{DEMO_EMAIL_DOMAIN}',
                },
            )
            out.append(cust)
        return out

    # --- Operaciones repartidas en el tiempo (facturas y compras) ---

    def _seed_invoices(self, customers, products, admin, months):
        sellable = [p for p in products if p.is_active and p.name not in RESERVED_LOW_STOCK]
        if Invoice.objects.filter(customer__email__endswith=f'@{DEMO_EMAIL_DOMAIN}').exists():
            return 0  # ya se generaron facturas demo en una corrida anterior

        rng = random.Random(42)
        now = timezone.now()
        created = 0
        for month_offset in range(months, 0, -1):
            month_dt = now - timedelta(days=30 * month_offset)
            for _ in range(rng.randint(5, 9)):
                customer = rng.choice(customers)
                invoice = Invoice.objects.create(customer=customer)
                chosen = rng.sample(sellable, min(rng.randint(1, 4), len(sellable)))
                subtotal = Decimal('0')
                for product in chosen:
                    qty = rng.randint(1, 6)
                    detail = InvoiceDetail.objects.create(
                        invoice=invoice, product=product, quantity=qty,
                        unit_price=product.unit_price)
                    subtotal += detail.subtotal
                    Product.objects.filter(pk=product.pk).update(
                        stock=Greatest(F('stock') - qty, 0))
                tax = (subtotal * Decimal('0.15')).quantize(Decimal('0.01'))
                invoice.subtotal, invoice.tax, invoice.total = subtotal, tax, subtotal + tax
                invoice.save(update_fields=['subtotal', 'tax', 'total'])
                asignar_datos_electronicos(invoice)

                inv_dt = month_dt.replace(day=1) + timedelta(days=rng.randint(0, 27))
                Invoice.objects.filter(pk=invoice.pk).update(invoice_date=inv_dt)

                if rng.random() < 0.7:  # ~70% ya pagadas, el resto queda pendiente
                    method = rng.choice(PAYMENT_METHODS)
                    pay_dt = inv_dt + timedelta(days=rng.randint(0, 5))
                    Invoice.objects.filter(pk=invoice.pk).update(
                        payment_status='PAGADA', payment_method=method, payment_date=pay_dt)
                    PaymentLog.objects.create(
                        invoice_id=invoice.pk, user=admin, method=method,
                        amount=invoice.total, note='Generado por seed_demo_data')
                created += 1
        return created

    def _seed_purchases(self, suppliers, products, months):
        restockable = [p for p in products if p.name not in RESERVED_LOW_STOCK]
        if Purchase.objects.filter(document_number__startswith='DEMO-').exists():
            return 0  # ya se generaron compras demo en una corrida anterior

        rng = random.Random(7)
        now = timezone.now()
        created = 0
        doc_seq = 1
        for month_offset in range(months, 0, -1):
            month_dt = now - timedelta(days=30 * month_offset)
            for _ in range(rng.randint(1, 3)):
                supplier = rng.choice(suppliers)
                purchase = Purchase.objects.create(
                    supplier=supplier, document_number=f'DEMO-{doc_seq:04d}')
                doc_seq += 1
                chosen = rng.sample(restockable, min(rng.randint(1, 3), len(restockable)))
                subtotal = Decimal('0')
                for product in chosen:
                    qty = rng.randint(10, 40)
                    cost = (product.unit_price * Decimal('0.6')).quantize(Decimal('0.01'))
                    detail = PurchaseDetail.objects.create(
                        purchase=purchase, product=product, quantity=qty, unit_cost=cost)
                    subtotal += detail.subtotal
                    Product.objects.filter(pk=product.pk).update(stock=F('stock') + qty)
                tax = (subtotal * Decimal('0.15')).quantize(Decimal('0.01'))
                purchase.subtotal, purchase.tax, purchase.total = subtotal, tax, subtotal + tax
                purchase.save(update_fields=['subtotal', 'tax', 'total'])

                pur_dt = month_dt.replace(day=1) + timedelta(days=rng.randint(0, 27))
                Purchase.objects.filter(pk=purchase.pk).update(purchase_date=pur_dt)
                created += 1
        return created
