import re
import unicodedata

from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User, Group, Permission


def generate_temp_password(first_name, last_name):
    """Inicial del primer nombre + primer apellido completo + inicial del
    segundo apellido, todo en minúsculas y sin tildes/ñ.
    Ej: 'Davis Steven' / 'Yanez Gualpa' -> 'dyanezg'."""
    def normalize(word):
        word = unicodedata.normalize('NFKD', word).encode('ascii', 'ignore').decode('ascii')
        return re.sub(r'[^a-zA-Z]', '', word).lower()

    nombres = [normalize(p) for p in first_name.strip().split() if normalize(p)]
    apellidos = [normalize(p) for p in last_name.strip().split() if normalize(p)]

    inicial_nombre = nombres[0][:1] if nombres else 'x'
    apellido1 = apellidos[0] if apellidos else 'user'
    inicial_apellido2 = apellidos[1][:1] if len(apellidos) > 1 else ''

    return f'{inicial_nombre}{apellido1}{inicial_apellido2}'


# === 1. CREACIÓN DE USUARIO CON ROL (solo Administrador) ===
class UserCreateForm(UserCreationForm):
    """El Administrador crea la cuenta y le asigna un rol. No hay
    autorregistro público: por eso esta vista está protegida en views.py.

    La contraseña puede ser manual (el admin la escribe, se valida con las
    reglas normales de Django) o automática (se genera con
    generate_temp_password y se salta la validación de fortaleza, porque a
    propósito es fácil de recordar — el usuario está obligado a cambiarla
    en su primer login, ver UserSecurityProfile.must_change_password)."""
    email = forms.EmailField(required=True)
    role = forms.ModelChoiceField(
        queryset=Group.objects.all(),
        required=True,
        label='Role',
        empty_label='-- Select a role --',
    )
    auto_password = forms.BooleanField(
        required=False, initial=True, label='Generar contraseña automáticamente',
    )

    class Meta:
        model = User
        fields = ['username', 'first_name', 'last_name', 'email', 'role',
                  'auto_password', 'password1', 'password2']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for f in self.fields:
            self.fields[f].widget.attrs['class'] = 'form-control'
        self.fields['auto_password'].widget.attrs['class'] = 'form-check-input'
        # No son obligatorios a nivel de widget: si se marca "automática",
        # se llenan solos en clean(); si no, clean() exige que se hayan escrito.
        self.fields['password1'].required = False
        self.fields['password2'].required = False
        self.fields['password1'].help_text = (
            'Déjalo vacío si vas a generar la contraseña automáticamente.'
        )

    def clean(self):
        cleaned_data = super().clean()
        if cleaned_data.get('auto_password'):
            temp_password = generate_temp_password(
                cleaned_data.get('first_name', ''), cleaned_data.get('last_name', '')
            )
            cleaned_data['password1'] = temp_password
            cleaned_data['password2'] = temp_password
        else:
            if not cleaned_data.get('password1') or not cleaned_data.get('password2'):
                self.add_error(
                    'password1',
                    'Escribe una contraseña o marca "Generar automáticamente".'
                )
        return cleaned_data

    def _post_clean(self):
        # UserCreationForm._post_clean() valida la fortaleza de la
        # contraseña (longitud, similitud con el usuario, etc.) — eso
        # rechazaría siempre la contraseña automática por diseño (es
        # deliberadamente corta y parecida al nombre/usuario). Para la
        # automática nos quedamos solo con la parte de ModelForm
        # (construye la instancia), sin esa validación de fortaleza.
        if self.cleaned_data.get('auto_password'):
            forms.ModelForm._post_clean(self)
        else:
            super()._post_clean()

    def save(self, commit=True):
        user = super().save(commit)
        if commit:
            # Asignar el rol elegido al nuevo usuario
            user.groups.add(self.cleaned_data['role'])
        return user

# === 2. EDICIÓN DE USUARIO (asignar roles) ===
class UserUpdateForm(forms.ModelForm):
    """El Administrador edita datos y roles de un usuario."""
    groups = forms.ModelMultipleChoiceField(
        queryset=Group.objects.all(),
        required=False,
        widget=forms.CheckboxSelectMultiple,
        label='Roles',
    )

    class Meta:
        model = User
        fields = ['username', 'first_name', 'last_name', 'email',
                  'is_active', 'groups']
        widgets = {
            'username': forms.TextInput(attrs={'class': 'form-control'}),
            'first_name': forms.TextInput(attrs={'class': 'form-control'}),
            'last_name': forms.TextInput(attrs={'class': 'form-control'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

# === 3. ROLES (Group) CON SUS PERMISOS ===
class GroupForm(forms.ModelForm):
    """Crear/editar un rol y marcar sus permisos con checkboxes."""
    permissions = forms.ModelMultipleChoiceField(
        queryset=Permission.objects.select_related('content_type'),
        required=False,
        widget=forms.CheckboxSelectMultiple,
        label='Permissions',
    )

    class Meta:
        model = Group
        fields = ['name', 'permissions']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
        }

# === 4. PERMISOS PERSONALIZADOS ===
class PermissionForm(forms.ModelForm):
    """Crear un permiso propio, ej: can_approve_invoice."""
    class Meta:
        model = Permission
        fields = ['name', 'codename', 'content_type']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'codename': forms.TextInput(attrs={'class': 'form-control'}),
            'content_type': forms.Select(attrs={'class': 'form-select'}),
        }
