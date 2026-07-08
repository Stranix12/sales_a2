from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.models import User, Group, Permission
from django.contrib.auth.views import LoginView, LogoutView
from django.db.models import Count
from django.shortcuts import redirect
from django.urls import reverse, reverse_lazy
from django.views import View
from django.views.generic import ListView, CreateView, UpdateView, DeleteView

from shared.emails import send_welcome_email
from shared.mixins import GroupRequiredMixin
from .forms import UserCreateForm, UserUpdateForm, GroupForm, PermissionForm

# === MIXIN BASE: SOLO ADMINISTRADOR ===
class AdminOnlyMixin(LoginRequiredMixin, GroupRequiredMixin):
    """Combina login + rol Administrador (el superusuario siempre pasa)."""
    group_required = ['Administrador']
    group_redirect_url = '/'

# === AUTENTICACIÓN (CBV) ===
class SecurityLoginView(LoginView):
    """Login con CBV. Reutiliza el template de la PARTE 9."""
    template_name = 'registration/login.html'

class SecurityLogoutView(LogoutView):
    """Logout con CBV. Redirige según LOGOUT_REDIRECT_URL."""
    pass

# === USUARIOS (solo Administrador) ===
class UserListView(AdminOnlyMixin, ListView):
    model = User
    template_name = 'security/user_list.html'
    context_object_name = 'items'

class UserCreateView(AdminOnlyMixin, CreateView):
    """No hay registro público: solo el Administrador crea usuarios."""
    model = User
    form_class = UserCreateForm
    template_name = 'security/user_form.html'
    success_url = reverse_lazy('security:user_list')
    extra_context = {'title': 'Create User'}

    def form_valid(self, form):
        # A propósito NO se llama a login() aquí: quien crea la cuenta es el
        # Administrador, no debe iniciar sesión como el usuario nuevo.
        response = super().form_valid(form)
        send_welcome_email(self.object)
        messages.success(self.request, f'Usuario "{self.object.username}" creado.')
        return response

class UserUpdateView(AdminOnlyMixin, UpdateView):
    model = User
    form_class = UserUpdateForm
    template_name = 'security/user_form.html'
    success_url = reverse_lazy('security:user_list')
    extra_context = {'title': 'Edit User'}

class UserDeleteView(AdminOnlyMixin, DeleteView):
    model = User
    template_name = 'security/confirm_delete.html'
    success_url = reverse_lazy('security:user_list')

# === ROLES / GROUP (solo Administrador) ===
# Consola de un solo panel: rail de roles (izquierda) + grilla de permisos del
# rol seleccionado (derecha). group_list ya no lista en tabla: entra directo
# a la consola (editar el primer rol, o crear uno si no existe ninguno).

# Apps que no se exponen en la grilla de permisos (infra de Django, no hay
# pantallas de negocio para LogEntry/ContentType/Session en este sistema).
PERMISSION_EXCLUDED_APPS = {'admin', 'contenttypes', 'sessions'}
PERMISSION_ACTIONS = ['view', 'add', 'change', 'delete']
ROLE_COLORS = ['#33459b', '#1e9e6d', '#b9790f', '#2f6fed', '#a23e9c', '#0f9aa0']
# Módulos de negocio primero (los que más se editan); auth (usuarios/roles) al final.
PERMISSION_APP_ORDER = {'billing': 0, 'purchasing': 1, 'auth': 2}


def _roles_with_colors():
    """Todos los roles con conteos (para el rail) y un color determinístico
    por posición, para diferenciarlos visualmente."""
    groups = list(
        Group.objects.order_by('name').annotate(
            perm_count=Count('permissions', distinct=True),
            user_count=Count('user', distinct=True),
        )
    )
    for i, g in enumerate(groups):
        g.color = ROLE_COLORS[i % len(ROLE_COLORS)]
    return groups


def _permission_matrix(selected_ids):
    """Agrupa los permisos por modelo (content type) con sus 4 acciones CRUD,
    marcando cada uno como seleccionado o no para el rol actual."""
    permissions = (
        Permission.objects
        .select_related('content_type')
        .exclude(content_type__app_label__in=PERMISSION_EXCLUDED_APPS)
        .order_by('content_type__app_label', 'content_type__model')
    )
    matrix = {}
    for perm in permissions:
        ct = perm.content_type
        key = (ct.app_label, ct.model)
        if key not in matrix:
            model_class = ct.model_class()
            label = model_class._meta.verbose_name.title() if model_class else ct.model
            matrix[key] = {'label': label, 'code': f'{ct.app_label}.{ct.model}', 'actions': {}}
        for action in PERMISSION_ACTIONS:
            if perm.codename == f'{action}_{ct.model}':
                perm.checked = perm.id in selected_ids
                matrix[key]['actions'][action] = perm
    return sorted(
        matrix.values(),
        key=lambda m: (PERMISSION_APP_ORDER.get(m['code'].split('.')[0], 99), m['label']),
    )


class GroupListView(AdminOnlyMixin, View):
    """/roles/ ya no es una tabla: redirige a la consola de un solo panel."""
    def get(self, request, *args, **kwargs):
        first = Group.objects.order_by('name').first()
        if first:
            return redirect('security:group_update', pk=first.pk)
        return redirect('security:group_create')


class GroupConsoleMixin:
    """Contexto compartido por crear/editar rol: roles para el rail y la
    grilla de permisos del panel derecho."""
    template_name = 'security/group_console.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        all_groups = _roles_with_colors()
        ctx['all_groups'] = all_groups
        ctx['object_color'] = next(
            (g.color for g in all_groups if self.object and g.pk == self.object.pk), '#9aa1b2'
        )

        form = ctx['form']
        if form.is_bound:
            # Re-render tras un error de validación: conserva lo que el
            # usuario acababa de marcar, no lo que hay guardado en BD.
            selected_ids = {int(v) for v in (form['permissions'].value() or [])}
        elif self.object:
            selected_ids = set(self.object.permissions.values_list('id', flat=True))
        else:
            selected_ids = set()

        matrix = _permission_matrix(selected_ids)
        ctx['permission_matrix'] = matrix
        ctx['total_permissions'] = sum(len(m['actions']) for m in matrix)
        ctx['selected_count'] = sum(
            1 for m in matrix for perm in m['actions'].values() if perm.checked
        )
        return ctx


class GroupCreateView(GroupConsoleMixin, AdminOnlyMixin, CreateView):
    model = Group
    form_class = GroupForm

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, f'Rol "{self.object.name}" creado.')
        return response

    def get_success_url(self):
        return reverse('security:group_update', kwargs={'pk': self.object.pk})


class GroupUpdateView(GroupConsoleMixin, AdminOnlyMixin, UpdateView):
    model = Group
    form_class = GroupForm

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, f'Rol "{self.object.name}" actualizado.')
        return response

    def get_success_url(self):
        return reverse('security:group_update', kwargs={'pk': self.object.pk})


class GroupDeleteView(AdminOnlyMixin, DeleteView):
    model = Group
    template_name = 'security/confirm_delete.html'
    success_url = reverse_lazy('security:group_list')

# === PERMISOS / PERMISSION (solo Administrador) ===
class PermissionListView(AdminOnlyMixin, ListView):
    model = Permission
    template_name = 'security/permission_list.html'
    context_object_name = 'items'
    queryset = Permission.objects.select_related('content_type')

class PermissionCreateView(AdminOnlyMixin, CreateView):
    model = Permission
    form_class = PermissionForm
    template_name = 'security/permission_form.html'
    success_url = reverse_lazy('security:permission_list')

class PermissionUpdateView(AdminOnlyMixin, UpdateView):
    model = Permission
    form_class = PermissionForm
    template_name = 'security/permission_form.html'
    success_url = reverse_lazy('security:permission_list')

class PermissionDeleteView(AdminOnlyMixin, DeleteView):
    model = Permission
    template_name = 'security/confirm_delete.html'
    success_url = reverse_lazy('security:permission_list')
