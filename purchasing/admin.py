from django.contrib import admin
from .models import Purchase, PurchaseDetail


class PurchaseDetailInline(admin.TabularInline):
    model = PurchaseDetail
    extra = 1


@admin.register(Purchase)
class PurchaseAdmin(admin.ModelAdmin):
    inlines = [PurchaseDetailInline]
    list_display = ['id', 'supplier', 'document_number', 'purchase_date', 'total']
