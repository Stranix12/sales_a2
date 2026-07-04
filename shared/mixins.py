from django.contrib import messages
from django.shortcuts import redirect


class StaffRequiredMixin:
    """Mixin que verifica si el usuario es miembro del staff.

    Si no es staff, redirige con un mensaje de error. Pensado para proteger las
    vistas de eliminación: cualquier usuario logueado puede ver y crear, pero
    solo el personal autorizado (is_staff) puede borrar.

    Uso:
        class ProductDeleteView(LoginRequiredMixin, StaffRequiredMixin, DeleteView):
            ...
            staff_redirect_url = '/products/'
    """
    staff_redirect_url = '/'
    staff_error_message = 'No tienes permiso para realizar esta acción. Se requiere acceso de staff.'

    def dispatch(self, request, *args, **kwargs):
        # dispatch() se ejecuta antes que la vista: verificamos permisos aquí.
        if not request.user.is_authenticated or not request.user.is_staff:
            messages.error(request, self.staff_error_message)
            return redirect(self.staff_redirect_url)
        return super().dispatch(request, *args, **kwargs)
