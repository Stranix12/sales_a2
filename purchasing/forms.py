from django import forms
from django.forms import inlineformset_factory
from billing.models import Supplier
from .models import Purchase, PurchaseDetail


class PurchaseForm(forms.ModelForm):
    class Meta:
        model = Purchase
        fields = ['supplier', 'document_number']


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
