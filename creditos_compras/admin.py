from django.contrib import admin

from creditos_ventas.admin import ReadOnlyDeleteMixin
from .models import CuotaCompra, PagoCuotaCompra


class PagoCuotaCompraInline(admin.TabularInline):
    model = PagoCuotaCompra
    extra = 0
    can_delete = False


@admin.register(CuotaCompra)
class CuotaCompraAdmin(ReadOnlyDeleteMixin, admin.ModelAdmin):
    list_display = ['compra', 'numero', 'fecha_vencimiento', 'valor', 'saldo', 'estado']
    list_filter = ['estado']
    search_fields = ['compra__document_number']
    inlines = [PagoCuotaCompraInline]
