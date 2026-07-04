import logging
from functools import wraps

from django.utils import timezone

# Logger de auditoría (los mensajes pueden redirigirse a archivo desde settings).
logger = logging.getLogger('audit')


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
