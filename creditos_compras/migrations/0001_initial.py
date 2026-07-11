"""Modelos del crédito de compras, trasladados desde creditos_ventas.

Las tablas ya existen (las creó creditos_ventas.0001_initial) y pueden tener
datos en producción, así que aquí NO se crean tablas: en el estado de Django
se registran los modelos bajo esta app (state_operations) y en la base de
datos solo se renombran las tablas al nombre que Django espera para esta app
(database_operations con ALTER TABLE ... RENAME). Depende de la migración
0002 de creditos_ventas, que saca estos modelos del estado de aquella app.
"""
import django.core.validators
import django.db.models.deletion
from decimal import Decimal
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('purchasing', '0002_purchase_estado_purchase_saldo_purchase_tipo_pago'),
        ('creditos_ventas', '0002_mover_cuotacompra_a_creditos_compras'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.CreateModel(
                    name='CuotaCompra',
                    fields=[
                        ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                        ('numero', models.PositiveIntegerField()),
                        ('fecha_vencimiento', models.DateField()),
                        ('valor', models.DecimalField(decimal_places=2, max_digits=12, validators=[django.core.validators.MinValueValidator(Decimal('0.01'))])),
                        ('saldo', models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                        ('estado', models.CharField(choices=[('PENDIENTE', 'Pendiente'), ('PAGADA', 'Pagada')], default='PENDIENTE', max_length=15)),
                        ('compra', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='cuotas', to='purchasing.purchase')),
                    ],
                    options={
                        'ordering': ['compra_id', 'numero'],
                    },
                ),
                migrations.CreateModel(
                    name='PagoCuotaCompra',
                    fields=[
                        ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                        ('fecha', models.DateField()),
                        ('valor', models.DecimalField(decimal_places=2, max_digits=12, validators=[django.core.validators.MinValueValidator(Decimal('0.01'))])),
                        ('observacion', models.TextField(blank=True)),
                        ('cuota', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='pagos', to='creditos_compras.cuotacompra')),
                    ],
                    options={
                        'ordering': ['-fecha', '-id'],
                    },
                ),
                migrations.AddConstraint(
                    model_name='cuotacompra',
                    constraint=models.UniqueConstraint(fields=('compra', 'numero'), name='unique_cuota_compra_numero'),
                ),
            ],
            database_operations=[
                migrations.RunSQL(
                    sql='ALTER TABLE creditos_ventas_cuotacompra RENAME TO creditos_compras_cuotacompra;',
                    reverse_sql='ALTER TABLE creditos_compras_cuotacompra RENAME TO creditos_ventas_cuotacompra;',
                ),
                migrations.RunSQL(
                    sql='ALTER TABLE creditos_ventas_pagocuotacompra RENAME TO creditos_compras_pagocuotacompra;',
                    reverse_sql='ALTER TABLE creditos_compras_pagocuotacompra RENAME TO creditos_ventas_pagocuotacompra;',
                ),
            ],
        ),
    ]
