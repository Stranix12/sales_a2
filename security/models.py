from django.conf import settings
from django.db import models


class UserSecurityProfile(models.Model):
    """Datos de seguridad que django.contrib.auth.User no trae de fábrica.

    Por ahora solo guarda si el usuario debe cambiar su contraseña en el
    próximo login (se marca en True cuando el Administrador le crea la
    cuenta, sea con contraseña automática o manual)."""
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='security_profile'
    )
    must_change_password = models.BooleanField(default=False)

    def __str__(self):
        return f'Perfil de seguridad de {self.user}'
