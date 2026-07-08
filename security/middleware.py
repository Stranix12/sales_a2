from django.shortcuts import redirect

# Rutas a las que un usuario con must_change_password=True sí puede entrar,
# para no dejarlo atrapado sin poder ni cambiar la contraseña ni cerrar sesión.
EXEMPT_PATHS = ('/accounts/logout/', '/security/logout/', '/security/force-password-change/')


class ForcePasswordChangeMiddleware:
    """Si el usuario tiene pendiente cambiar su contraseña (se la asignó el
    Administrador al crear la cuenta), lo manda directo a cambiarla antes
    de dejarlo usar el resto del sistema."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = request.user
        if user.is_authenticated and request.path not in EXEMPT_PATHS:
            profile = getattr(user, 'security_profile', None)
            if profile and profile.must_change_password:
                return redirect('security:force_password_change')
        return self.get_response(request)
