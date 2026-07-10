from django import forms
from django.forms import inlineformset_factory
from billing.models import Supplier
from creditos_ventas.forms import tipo_pago_field, num_cuotas_field, validar_tipo_pago
from .models import Purchase, PurchaseDetail


class PurchaseForm(forms.ModelForm):
    """tipo_pago/num_cuotas: ver el comentario equivalente en
    billing.forms.InvoiceForm — mismo patrón, misma app creditos_ventas."""
    tipo_pago = tipo_pago_field()
    num_cuotas = num_cuotas_field()

    class Meta:
        model = Purchase
        fields = ['supplier', 'document_number']

    def clean(self):
        cleaned_data = super().clean()
        return validar_tipo_pago(self, cleaned_data)


PurchaseDetailFormSet = inlineformset_factory(
    Purchase,
    PurchaseDetail,
    fields=['product', 'quantity', 'unit_cost'],
    widgets={
        'product': forms.Select(attrs={'class': 'form-select'}),
        'quantity': forms.NumberInput(attrs={'class': 'form-control', 'min': '1', 'placeholder': '1'}),
        'unit_cost': forms.NumberInput(attrs={'class': 'form-control', 'min': '0', 'step': '0.01', 'placeholder': '0.00'}),
    },
    extra=1,
    can_delete=True,
)


class PurchaseFilterForm(forms.Form):
    supplier = forms.ModelChoiceField(
        queryset=Supplier.objects.all(), required=False, empty_label='Todos los proveedores',
        widget=forms.Select(attrs={'class': 'form-select'}))
    date_from = forms.DateField(required=False,
                                widget=forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}))
    date_to = forms.DateField(required=False,
                              widget=forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}))
    year = forms.IntegerField(required=False,
                              widget=forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'Año'}))
