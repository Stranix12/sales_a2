from django.core.exceptions import ValidationError


def validate_cedula_ec(value):
    """Valida cédula ecuatoriana (10 dígitos) o RUC (13 dígitos) usando el
    algoritmo oficial del Registro Civil (módulo 10).

    Uso en el modelo:
        from shared.validators import validate_cedula_ec
        dni = models.CharField(max_length=13, validators=[validate_cedula_ec])
    """
    # Paso 1: solo números.
    if not value.isdigit():
        raise ValidationError('El DNI/RUC debe contener solo números.', code='invalid_chars')

    # Paso 2: longitud (cédula = 10, RUC = 13).
    if len(value) not in (10, 13):
        raise ValidationError('El DNI/RUC debe tener 10 dígitos (cédula) o 13 (RUC).',
                              code='invalid_length')

    # Paso 3: código de provincia (01-24).
    province = int(value[:2])
    if province < 1 or province > 24:
        raise ValidationError(f'Código de provincia inválido: {province:02d} (debe ser 01-24).',
                              code='invalid_province')

    # Paso 4: tercer dígito < 6 (persona natural).
    if int(value[2]) >= 6:
        raise ValidationError('El tercer dígito debe ser menor que 6 para personas naturales.',
                              code='invalid_third')

    # Paso 5: algoritmo módulo 10 sobre los primeros 9 dígitos.
    coefficients = [2, 1, 2, 1, 2, 1, 2, 1, 2]
    total = 0
    for i in range(9):
        result = int(value[i]) * coefficients[i]
        if result > 9:
            result -= 9
        total += result

    # Paso 6: dígito verificador.
    verifier = 10 - (total % 10)
    if verifier == 10:
        verifier = 0

    # Paso 7: comparar con el décimo dígito.
    if verifier != int(value[9]):
        raise ValidationError('Número de identificación inválido (dígito verificador incorrecto).',
                              code='invalid_verifier')

    return value
