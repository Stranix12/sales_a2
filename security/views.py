import json

from django.contrib import messages
from django.contrib.auth import login as auth_login
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.models import User, Group, Permission
from django.contrib.auth.views import LoginView, LogoutView, PasswordChangeView
from django.db.models import Count, Q
from django.shortcuts import redirect
from django.urls import reverse, reverse_lazy
from django.views import View
from django.views.generic import ListView, CreateView, UpdateView, DeleteView

from shared.emails import send_welcome_email
from shared.mixins import GroupRequiredMixin
from .forms import ClientSignupForm, UserCreateForm, UserUpdateForm, GroupForm, PermissionForm
from .models import UserSecurityProfile

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

class ClientSignupView(CreateView):
    """Registro público del portal: SOLO clientes se crean su propia cuenta
    aquí (los roles internos —Administrador, Vendedor, Analista de Compras—
    los sigue creando el Administrador desde /security/users/create/)."""
    model = User
    form_class = ClientSignupForm
    template_name = 'security/client_signup.html'

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            return redirect('billing:home')
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        response = super().form_valid(form)
        # A diferencia de UserCreateView (el Administrador crea la cuenta de
        # otro y no debe iniciar sesión como esa persona), aquí el propio
        # cliente acaba de definir su contraseña: se le deja entrado.
        auth_login(self.request, self.object, backend='django.contrib.auth.backends.ModelBackend')
        login_url = self.request.build_absolute_uri(reverse('login'))
        send_welcome_email(self.object, login_url=login_url)
        messages.success(self.request, f'¡Bienvenido, {self.object.first_name}! Tu cuenta fue creada.')
        return response

    def get_success_url(self):
        return reverse('billing:portal_catalog')

class ForcePasswordChangeView(PasswordChangeView):
    """A donde ForcePasswordChangeMiddleware redirige a un usuario con
    contraseña temporal pendiente de cambiar. PasswordChangeView ya exige
    login por su cuenta (login_required en su dispatch)."""
    template_name = 'security/force_password_change.html'
    success_url = reverse_lazy('billing:home')

    def form_valid(self, form):
        response = super().form_valid(form)
        UserSecurityProfile.objects.filter(user=self.request.user).update(
            must_change_password=False
        )
        messages.success(self.request, 'Contraseña actualizada correctamente.')
        return response

# === USUARIOS (solo Administrador) ===
class UserListView(AdminOnlyMixin, ListView):
    """Listado de usuarios con tarjetas por rol: cada tarjeta filtra la tabla
    (?rol=<id> | ?rol=sin-rol | sin parámetro = todos)."""
    model = User
    template_name = 'security/user_list.html'
    context_object_name = 'items'

    def get_queryset(self):
        qs = User.objects.prefetch_related('groups').order_by('username')
        self.rol = self.request.GET.get('rol') or ''
        if self.rol == 'sin-rol':
            qs = qs.filter(groups__isnull=True)
        elif self.rol.isdigit():
            qs = qs.filter(groups__pk=self.rol)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['roles'] = _roles_with_colors()  # nombre + color + user_count
        ctx['total_users'] = User.objects.count()
        ctx['sin_rol_count'] = User.objects.filter(groups__isnull=True).count()
        ctx['rol_activo'] = self.rol
        return ctx

class UserCreateView(AdminOnlyMixin, CreateView):
    """No hay registro público: solo el Administrador crea usuarios."""
    model = User
    form_class = UserCreateForm
    template_name = 'security/user_form.html'
    success_url = reverse_lazy('security:user_list')
    extra_context = {'title': 'Nuevo usuario'}

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        # Datos de los clientes vinculables para que el template autollene
        # Nombre/Apellidos/Email al elegir uno (rol Cliente).
        ctx['customers_json'] = json.dumps({
            str(c.pk): {'first_name': c.first_name, 'last_name': c.last_name,
                        'email': c.email or '', 'dni': c.dni}
            for c in ctx['form'].fields['customer'].queryset
        })
        return ctx

    def form_valid(self, form):
        # A propósito NO se llama a login() aquí: quien crea la cuenta es el
        # Administrador, no debe iniciar sesión como el usuario nuevo.
        response = super().form_valid(form)
        # La contraseña (automática o manual) es asignada por el admin, no
        # elegida por el propio usuario: se le exige cambiarla al primer login.
        UserSecurityProfile.objects.update_or_create(
            user=self.object, defaults={'must_change_password': True}
        )
        temp_password = form.cleaned_data.get('password1')
        login_url = self.request.build_absolute_uri(reverse('login'))
        send_welcome_email(self.object, temp_password=temp_password, login_url=login_url)
        messages.success(self.request, f'Usuario "{self.object.username}" creado.')
        return response

class UserUpdateView(AdminOnlyMixin, UpdateView):
    model = User
    form_class = UserUpdateForm
    template_name = 'security/user_form.html'
    success_url = reverse_lazy('security:user_list')
    extra_context = {'title': 'Editar usuario'}

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
PERMISSION_APP_ORDER = {'billing': 0, 'purchasing': 1, 'creditos_ventas': 2,
                        'creditos_compras': 3, 'facturacion_electronica': 4, 'auth': 5}


def _roles_with_colors():
    """Todos los roles con conteos (para el rail) y un color determinístico
    por posición, para diferenciarlos visualmente."""
    groups = list(
        Group.objects.order_by('name').annotate(
            # Solo permisos VISIBLES en la grilla (se excluyen las apps internas
            # de Django) para que el conteo del rail cuadre con el del panel.
            perm_count=Count(
                'permissions', distinct=True,
                filter=~Q(permissions__content_type__app_label__in=PERMISSION_EXCLUDED_APPS),
            ),
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

    def get_context_data(self, **kwargs):
        """Agrupa los permisos por modelo (content type) para mostrarlos como
        tarjetas en vez de una tabla plana. Los módulos de negocio primero."""
        ctx = super().get_context_data(**kwargs)
        groups = {}
        for p in self.object_list.order_by('content_type__app_label',
                                           'content_type__model', 'codename'):
            ct = p.content_type
            key = (ct.app_label, ct.model)
            if key not in groups:
                model_class = ct.model_class()
                label = model_class._meta.verbose_name.title() if model_class else ct.model
                groups[key] = {'label': label, 'app': ct.app_label,
                               'code': f'{ct.app_label}.{ct.model}', 'perms': []}
            groups[key]['perms'].append(p)
        order = {'billing': 0, 'purchasing': 1, 'auth': 2}
        ctx['permission_groups'] = sorted(
            groups.values(), key=lambda g: (order.get(g['app'], 9), g['label']))
        return ctx

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
