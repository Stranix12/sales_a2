"""Lógica de negocio del crédito de ventas.

La implementación real (`_generar_cuotas`/`_registrar_pagos`) está
parametrizada por modelo y nombre de FK porque el algoritmo es idéntico para
ventas y compras: la app creditos_compras la reutiliza aplicándola a
Purchase + CuotaCompra en lugar de Invoice + CuotaVenta, así la lógica no se
duplica en dos apps.
"""
from calendar import monthrange
from decimal import Decimal, ROUND_DOWN

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from billing.models import PaymentLog
from .models import CuotaVenta, PagoCuotaVenta


def _add_months(base_date, months):
    """Suma `months` meses a `base_date`, recortando el día si el mes
    destino es más corto (ej. 31 ene + 1 mes -> 28/29 feb)."""
    month_index = base_date.month - 1 + months
    year = base_date.year + month_index // 12
    month = month_index % 12 + 1
    day = min(base_date.day, monthrange(year, month)[1])
    return base_date.replace(year=year, month=month, day=day)


def _fecha_documento(documento):
    """Invoice.invoice_date y Purchase.purchase_date son DateTimeField
    (auto_now_add): se normaliza a date para comparar con fechas de pago."""
    fecha = getattr(documento, 'invoice_date', None) or getattr(documento, 'purchase_date', None)
    return fecha.date() if hasattr(fecha, 'date') else fecha


def _generar_cuotas(documento, num_cuotas, *, cuota_model, doc_attr):
    if documento.estado == 'PAGADA':
        raise ValidationError('No se pueden generar cuotas: el documento ya está pagado.')
    if cuota_model.objects.filter(**{doc_attr: documento}).exists():
        raise ValidationError('Este documento ya tiene un plan de cuotas generado.')
    if not num_cuotas or num_cuotas < 1:
        raise ValidationError('La cantidad de cuotas debe ser al menos 1.')

    total = documento.total
    # Redondeo hacia abajo en cada cuota; la última se lleva el residuo, así
    # la suma de las cuotas siempre cuadra exacto con el total.
    base = (total / num_cuotas).quantize(Decimal('0.01'), rounding=ROUND_DOWN)
    fecha_base = _fecha_documento(documento)

    cuotas = []
    acumulado = Decimal('0.00')
    with transaction.atomic():
        for i in range(1, num_cuotas + 1):
            valor = base if i < num_cuotas else (total - acumulado)
            acumulado += valor
            cuota = cuota_model.objects.create(
                **{doc_attr: documento},
                numero=i,
                fecha_vencimiento=_add_months(fecha_base, i),
                valor=valor,
                saldo=valor,
                estado='PENDIENTE',
            )
            cuotas.append(cuota)

        documento.tipo_pago = 'CREDITO'
        documento.saldo = total
        documento.estado = 'PENDIENTE'
        documento.save(update_fields=['tipo_pago', 'saldo', 'estado'])

    return cuotas


def _sincronizar_documento(documento, doc_attr, cuota_model, user=None):
    """Recalcula el saldo del documento a partir de sus cuotas y, si ya no
    queda saldo pendiente, lo marca PAGADA (y sincroniza payment_status en
    el caso de Invoice, para que el resto de la app deje de ofrecer cobrarla
    de nuevo)."""
    saldo = cuota_model.objects.filter(**{doc_attr: documento}).aggregate(
        s=Sum('saldo'))['s'] or Decimal('0.00')
    documento.saldo = saldo

    if saldo > 0:
        documento.save(update_fields=['saldo'])
        return

    documento.estado = 'PAGADA'
    if doc_attr == 'factura':
        documento.payment_status = 'PAGADA'
        documento.payment_method = 'credito'
        documento.payment_date = timezone.now()
        documento.save(update_fields=['saldo', 'estado', 'payment_status', 'payment_method', 'payment_date'])
        PaymentLog.objects.create(
            invoice=documento, user=user, method='credito', amount=documento.total,
            note='Crédito liquidado: todas las cuotas quedaron pagadas.',
        )
    else:
        documento.save(update_fields=['saldo', 'estado'])


def _registrar_pagos(cuotas_con_montos, fecha, observacion, *, pago_model, doc_attr, user=None):
    """cuotas_con_montos: lista de (cuota, monto). Todo o nada: si una sola
    fila falla la validación, no se guarda ningún pago de este envío."""
    if not cuotas_con_montos:
        raise ValidationError('No se seleccionó ninguna cuota para pagar.')

    hoy = timezone.localdate()
    if fecha > hoy:
        raise ValidationError('La fecha de pago no puede ser futura.')

    cuota_model = type(cuotas_con_montos[0][0])
    doc_model = cuota_model._meta.get_field(doc_attr).related_model
    montos = {cuota.pk: monto for cuota, monto in cuotas_con_montos}

    pagos_creados = []
    with transaction.atomic():
        cuotas = {c.pk: c for c in cuota_model.objects.select_for_update().filter(pk__in=montos)}
        doc_ids = {getattr(c, f'{doc_attr}_id') for c in cuotas.values()}
        documentos = {d.pk: d for d in doc_model.objects.select_for_update().filter(pk__in=doc_ids)}

        for cuota_id, monto in montos.items():
            cuota = cuotas[cuota_id]
            documento = documentos[getattr(cuota, f'{doc_attr}_id')]

            if documento.estado == 'PAGADA':
                raise ValidationError(f'La cuota #{cuota.numero} pertenece a un documento que ya está pagado.')
            if fecha < _fecha_documento(documento):
                raise ValidationError('La fecha de pago no puede ser anterior a la fecha del documento.')
            if monto is None or monto <= 0:
                raise ValidationError(f'El monto a pagar de la cuota #{cuota.numero} debe ser mayor que cero.')
            if monto > cuota.saldo:
                raise ValidationError(
                    f'El monto a pagar de la cuota #{cuota.numero} no puede superar su saldo (${cuota.saldo}).')

            pago = pago_model.objects.create(cuota=cuota, fecha=fecha, valor=monto, observacion=observacion)
            pagos_creados.append(pago)

            cuota.saldo -= monto
            if cuota.saldo <= 0:
                cuota.saldo = Decimal('0.00')
                cuota.estado = 'PAGADA'
            cuota.save(update_fields=['saldo', 'estado'])

        for documento in documentos.values():
            _sincronizar_documento(documento, doc_attr, cuota_model, user=user)

    return pagos_creados


# --- API pública: venta ---
def generar_cuotas_venta(invoice, num_cuotas):
    return _generar_cuotas(invoice, num_cuotas, cuota_model=CuotaVenta, doc_attr='factura')


def registrar_pagos_venta(cuotas_con_montos, fecha, observacion='', user=None):
    return _registrar_pagos(cuotas_con_montos, fecha, observacion,
                            pago_model=PagoCuotaVenta, doc_attr='factura', user=user)
