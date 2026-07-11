"""Traslado de CuotaCompra/PagoCuotaCompra a la nueva app creditos_compras.

Esta migración solo saca los modelos del ESTADO de esta app (state_operations
sin database_operations): las tablas NO se tocan aquí. El rename físico de
las tablas lo hace creditos_compras.0001_initial, que depende de esta, así
los datos existentes (local y producción) se conservan íntegros.
"""
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('creditos_ventas', '0001_initial'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                # PagoCuotaCompra primero: tiene FK hacia CuotaCompra.
                migrations.DeleteModel(name='PagoCuotaCompra'),
                migrations.DeleteModel(name='CuotaCompra'),
            ],
            database_operations=[],
        ),
    ]
