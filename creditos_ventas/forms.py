"""Campos y formularios reutilizados por billing.forms/purchasing.forms
(registro del tipo de pago) y por las pantallas propias de esta app
(registrar pago de una o varias cuotas)."""
from decimal import Decimal

from django import forms
from django.utils import timezone

TIPO_PAGO_CHOICES = [('CONTADO', 'Contado'), ('CREDITO', 'Crédito')]


def tipo_pago_field():
    """Campo declarado (no de modelo) que InvoiceForm/PurchaseForm incluyen
    para elegir el tipo de pago al registrar la factura/compra. Devuelve una
    instancia NUEVA cada vez que se llama (los Field de Django no se
    comparten entre formularios distintos)."""
    return forms.ChoiceField(
        choices=TIPO_PAGO_CHOICES, initial='CONTADO', required=False,
        label='Tipo de pago',
        widget=forms.Select(attrs={'class': 'form-select', 'id': 'id_tipo_pago'}),
    )


def num_cuotas_field():
    """Cantidad de cuotas mensuales; solo obligatorio si tipo_pago=CREDITO
    (se valida en validar_tipo_pago, no aquí, porque depende del otro campo)."""
    return forms.IntegerField(
        required=False, min_value=1,
        label='Número de cuotas mensuales',
        help_text='Obligatorio solo si el tipo de pago es Crédito.',
        widget=forms.NumberInput(attrs={
            'class': 'form-control', 'min': '1', 'placeholder': 'Ej: 6', 'id': 'id_num_cuotas'}),
    )


def validar_tipo_pago(form, cleaned_data):
    """Normaliza tipo_pago (default CONTADO si no vino, para no romper
    formularios/tests que no envían el campo) y exige num_cuotas si es
    CREDITO. Modifica cleaned_data en sitio."""
    tipo_pago = cleaned_data.get('tipo_pago') or 'CONTADO'
    cleaned_data['tipo_pago'] = tipo_pago
    if tipo_pago == 'CREDITO':
        num_cuotas = cleaned_data.get('num_cuotas')
        if not num_cuotas or num_cuotas < 1:
            form.add_error('num_cuotas', 'Ingresa la cantidad de cuotas mensuales (mínimo 1).')
    return cleaned_data


class RegistrarPagoForm(forms.Form):
    """Cabecera del pago (fecha + observación), común a una o varias cuotas."""
    fecha = forms.DateField(
        initial=timezone.localdate,
        widget=forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
        label='Fecha de pago',
    )
    observacion = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 2,
                                     'placeholder': 'Observación (opcional)'}),
        label='Observación',
    )

    def clean_fecha(self):
        fecha = self.cleaned_data['fecha']
        if fecha > timezone.localdate():
            raise forms.ValidationError('La fecha de pago no puede ser futura.')
        return fecha


class CuotaPagoRowForm(forms.Form):
    """Una fila del formset: una cuota pendiente + cuánto se le abona."""
    cuota_id = forms.IntegerField(widget=forms.HiddenInput())
    pagar = forms.BooleanField(required=False, label='Pagar',
                               widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}))
    monto = forms.DecimalField(
        required=False, min_value=Decimal('0.01'), max_digits=12, decimal_places=2,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'placeholder': '0.00'}),
        label='Monto a pagar',
    )

    def clean(self):
        cleaned_data = super().clean()
        if cleaned_data.get('pagar') and not cleaned_data.get('monto'):
            self.add_error('monto', 'Ingresa el monto a pagar de esta cuota.')
        return cleaned_data


CuotaPagoFormSet = forms.formset_factory(CuotaPagoRowForm, extra=0)


class CuotaFilterForm(forms.Form):
    """Filtro del listado de cuotas pendientes (venta o compra)."""
    ESTADO_CHOICES = [('', 'Todas'), ('PENDIENTE', 'Pendientes'), ('PAGADA', 'Pagadas')]
    estado = forms.ChoiceField(
        required=False, choices=ESTADO_CHOICES, initial='PENDIENTE',
        widget=forms.Select(attrs={'class': 'form-select'}))
