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

class GroupRequiredMixin:
    """
    Mixin que verifica si el usuario pertenece a alguno
    de los roles (grupos) indicados en group_required.

    Uso:
        class GroupListView(LoginRequiredMixin, GroupRequiredMixin, ListView):
            group_required = ['Administrador']
    """
    group_required = []        # Lista de roles permitidos
    group_redirect_url = '/'   # A dónde redirigir si no tiene el rol
    group_error_message = 'You do not have permission to access this option.'

    def dispatch(self, request, *args, **kwargs):
        # 1. Si no inició sesión -> al login
        if not request.user.is_authenticated:
            return redirect('login')
        # 2. El superusuario siempre pasa
        if request.user.is_superuser:
            return super().dispatch(request, *args, **kwargs)
        # 3. ¿Pertenece a alguno de los roles permitidos?
        if request.user.groups.filter(name__in=self.group_required).exists():
            return super().dispatch(request, *args, **kwargs)
        # 4. No tiene el rol -> mensaje de error y redirección
        messages.error(request, self.group_error_message)
        return redirect(self.group_redirect_url)
