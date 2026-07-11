from django.contrib import admin
from .models import CuotaVenta, PagoCuotaVenta


class ReadOnlyDeleteMixin:
    """Las cuotas se generan automáticamente y los pagos son un registro de
    auditoría: no se permite borrarlos desde el admin (PROTECT ya lo impide
    a nivel de BD para cuotas con pagos; esto cierra también la puerta del
    admin para las que no tienen). Compartido con creditos_compras."""
    def has_delete_permission(self, request, obj=None):
        return False


class PagoCuotaVentaInline(admin.TabularInline):
    model = PagoCuotaVenta
    extra = 0
    can_delete = False


@admin.register(CuotaVenta)
class CuotaVentaAdmin(ReadOnlyDeleteMixin, admin.ModelAdmin):
    list_display = ['factura', 'numero', 'fecha_vencimiento', 'valor', 'saldo', 'estado']
    list_filter = ['estado']
    search_fields = ['factura__numero_factura']
    inlines = [PagoCuotaVentaInline]
