import logging
from functools import wraps

from django.core.exceptions import PermissionDenied
from django.utils import timezone

# Logger de auditoría (los mensajes pueden redirigirse a archivo desde settings).
logger = logging.getLogger('audit')


def any_permission_required(perms, raise_exception=True):
    """Como @permission_required, pero exige AL MENOS UNO de los permisos
    listados en perms, no todos. Equivalente FBV de
    shared.mixins.AnyPermissionRequiredMixin (para las pocas vistas de
    listado que son función en vez de ListView, p. ej. purchase_list).

    Uso:
        @login_required
        @any_permission_required(('purchasing.view_purchase', 'purchasing.add_purchase',
                                  'purchasing.change_purchase', 'purchasing.delete_purchase'))
        def purchase_list(request):
            ...
    """
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if any(request.user.has_perm(p) for p in perms):
                return view_func(request, *args, **kwargs)
            if raise_exception:
                raise PermissionDenied
            from django.contrib.auth.views import redirect_to_login
            return redirect_to_login(request.get_full_path())
        return wrapper
    return decorator


def audit_action(action_name):
    """Decorador que registra las acciones del usuario para auditoría.

    Args:
        action_name (str): nombre de la acción, p. ej. "CREATE_BRAND".

    Uso:
        @login_required
        @audit_action('CREATE_BRAND')
        def brand_create(request):
            ...
    """
    def decorator(view_func):
        @wraps(view_func)  # preserva el nombre/docstring de la vista original
        def wrapper(request, *args, **kwargs):
            user = request.user.username if request.user.is_authenticated else 'Anonymous'
            ip = request.META.get('REMOTE_ADDR', 'unknown')
            method = request.method
            timestamp = timezone.now().strftime('%Y-%m-%d %H:%M:%S')
            path = request.path

            line = (f'[AUDIT] {timestamp} | User: {user} | Action: {action_name} | '
                    f'Method: {method} | Path: {path} | IP: {ip}')
            logger.info(line)
            print('\n' + line)

            response = view_func(request, *args, **kwargs)

            if method == 'POST':
                print(f'[AUDIT] {timestamp} | COMPLETED: {action_name} by {user}')
            return response
        return wrapper
    return decorator
