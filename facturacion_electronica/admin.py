from django.contrib import admin

from .models import ComprobanteElectronico


@admin.register(ComprobanteElectronico)
class ComprobanteElectronicoAdmin(admin.ModelAdmin):
    list_display = ['invoice', 'estado', 'ambiente', 'numero_autorizacion', 'fecha_autorizacion']
    list_filter = ['estado', 'ambiente']
    search_fields = ['clave_acceso', 'numero_autorizacion', 'invoice__numero_factura']
    readonly_fields = ['clave_acceso', 'numero_autorizacion', 'fecha_autorizacion',
                       'xml_generado', 'xml_autorizado', 'mensajes', 'created_at', 'updated_at']

    def has_delete_permission(self, request, obj=None):
        return False
