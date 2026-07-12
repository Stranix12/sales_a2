"""Suite de tests de security: recuperación de contraseña por correo,
correo de bienvenida al inscribir usuarios, y roles (pantallas + acceso).

Corre con: python manage.py test security
"""
import re
from decimal import Decimal

from django.contrib.auth.models import Group, User
from django.core import mail
from django.core.management import call_command
from django.test import Client, TestCase

from billing.models import Customer, Invoice
from .models import UserSecurityProfile


class PasswordResetFlowTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            'pwreset_user', email='pwreset@example.com', password='ViejaClave123!')

    def setUp(self):
        self.client = Client()

    def _extract_reset_link(self, body):
        m = re.search(r'https?://[^\s]+/accounts/reset/[^\s]+/[^\s]+/', body)
        self.assertIsNotNone(m, f'no se encontró el link de reset en el correo:\n{body}')
        return m.group(0).replace('http://testserver', '').replace('https://testserver', '')

    def test_formulario_de_recuperacion_renderiza(self):
        r = self.client.get('/accounts/password_reset/')
        self.assertEqual(r.status_code, 200)
        self.assertIn('Escribe tu email', r.content.decode())

    def test_solicitar_reset_envia_correo_con_link_valido(self):
        r = self.client.post('/accounts/password_reset/', {'email': 'pwreset@example.com'}, follow=True)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('Recupera tu contraseña', mail.outbox[0].subject)
        self.assertEqual(mail.outbox[0].to, ['pwreset@example.com'])

    def test_email_inexistente_no_revela_nada_y_no_envia_correo(self):
        r = self.client.post('/accounts/password_reset/', {'email': 'no-existe@example.com'}, follow=True)
        self.assertEqual(r.status_code, 200)  # misma pantalla de "revisa tu correo", no filtra si existe o no
        self.assertEqual(len(mail.outbox), 0)

    def test_flujo_completo_cambiar_contrasena_con_el_link(self):
        self.client.post('/accounts/password_reset/', {'email': 'pwreset@example.com'})
        link = self._extract_reset_link(mail.outbox[0].body)

        # 1er GET al link: válido, muestra el formulario de nueva contraseña
        r1 = self.client.get(link, follow=True)
        self.assertContains(r1, 'Elige tu nueva contraseña')

        # Enviar la nueva contraseña (la vista ya redirigió internamente a
        # la URL "set-password" tras el primer GET; seguimos la sesión)
        r2 = self.client.post(r1.redirect_chain[-1][0] if r1.redirect_chain else link, {
            'new_password1': 'NuevaClaveSegura456!',
            'new_password2': 'NuevaClaveSegura456!',
        }, follow=True)
        self.assertContains(r2, '¡Listo!')

        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('NuevaClaveSegura456!'))
        self.assertFalse(self.user.check_password('ViejaClave123!'))

    def test_link_ya_usado_no_vuelve_a_funcionar(self):
        self.client.post('/accounts/password_reset/', {'email': 'pwreset@example.com'})
        link = self._extract_reset_link(mail.outbox[0].body)
        r1 = self.client.get(link, follow=True)
        set_url = r1.redirect_chain[-1][0] if r1.redirect_chain else link
        self.client.post(set_url, {'new_password1': 'OtraClave789!', 'new_password2': 'OtraClave789!'})

        # Reusar el link original (mismo uid/token) ya no debe ser válido:
        # el hash del token depende del password, que ya cambió.
        r_reuse = self.client.get(link, follow=True)
        self.assertContains(r_reuse, 'no es válido o ya expiró')

    def test_link_de_login_a_recuperacion_presente(self):
        r = self.client.get('/accounts/login/')
        self.assertIn('¿Olvidaste tu contraseña?', r.content.decode())


# =====================================================================
# Correo de bienvenida al inscribir un usuario
# =====================================================================
class UserCreateWelcomeEmailTests(TestCase):
    """Al crear un usuario, le debe llegar el correo de bienvenida con su
    contraseña temporal, el rol asignado y el link de acceso; y el sistema
    debe obligarlo a cambiar esa contraseña en su primer login."""
    @classmethod
    def setUpTestData(cls):
        call_command('setup_roles')
        cls.admin = User.objects.create_superuser('admin_welcome', 'a@a.com', 'pass12345')

    def setUp(self):
        self.client = Client()
        self.client.force_login(self.admin)

    def _post(self, extra=None):
        data = {
            'username': 'nuevo_vendedor',
            'first_name': 'Davis Steven', 'last_name': 'Yanez Gualpa',
            'email': 'nuevo@example.com',
            'role': Group.objects.get(name='Vendedor').pk,
            'auto_password': 'on', 'password1': '', 'password2': '',
        }
        data.update(extra or {})
        return self.client.post('/security/users/create/', data, follow=True)

    def test_crear_usuario_envia_correo_de_bienvenida(self):
        self._post()
        self.assertTrue(User.objects.filter(username='nuevo_vendedor').exists())
        self.assertEqual(len(mail.outbox), 1)
        correo = mail.outbox[0]
        self.assertEqual(correo.to, ['nuevo@example.com'])
        self.assertIn('Bienvenido', correo.subject)
        self.assertIn('dyanezg', correo.body)           # contraseña temporal generada
        self.assertIn('/accounts/login/', correo.body)  # link de acceso
        self.assertIn('Vendedor', correo.body)          # rol asignado

    def test_contrasena_temporal_valida_y_cambio_obligatorio(self):
        self._post()
        user = User.objects.get(username='nuevo_vendedor')
        self.assertTrue(user.check_password('dyanezg'))
        self.assertTrue(UserSecurityProfile.objects.get(user=user).must_change_password)

    def test_rol_cliente_vincula_el_customer_y_envia_correo(self):
        customer = Customer.objects.create(
            dni='1710034065', first_name='Pedro', last_name='Yanez',
            email='pedro@example.com')
        self._post({
            # El username que se escriba se ignora para el rol Cliente: el
            # servidor lo reemplaza por la cédula del cliente vinculado (ver
            # UserCreateForm.clean), para que sea consistente con el login
            # por cédula del autorregistro público.
            'username': 'nombre-a-ignorar', 'first_name': 'Pedro', 'last_name': 'Yanez',
            'email': 'pedro@example.com',
            'role': Group.objects.get(name='Cliente').pk,
            'customer': customer.pk,
        })
        user = User.objects.get(username=customer.dni)
        customer.refresh_from_db()
        self.assertEqual(customer.user, user)  # cuenta vinculada a su cliente
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ['pedro@example.com'])

    def test_rol_cliente_sin_customer_es_rechazado(self):
        r = self._post({'role': Group.objects.get(name='Cliente').pk})
        self.assertFalse(User.objects.filter(username='nuevo_vendedor').exists())
        self.assertEqual(len(mail.outbox), 0)
        self.assertIn('requiere elegir', r.content.decode())


# =====================================================================
# Autorregistro público de clientes (/security/registro/)
# =====================================================================
class ClientSignupTests(TestCase):
    """Solo los clientes se crean su propia cuenta aquí; inician sesión con
    su cédula (no eligen un usuario) y quedan logueados de inmediato."""
    @classmethod
    def setUpTestData(cls):
        call_command('setup_roles')

    def setUp(self):
        self.client = Client()

    def _post(self, extra=None):
        data = {
            'dni': '1710034065', 'first_name': 'Pedro', 'last_name': 'Yanez',
            'email': 'pedro@example.com', 'phone': '0999999999', 'address': '',
            'password1': 'ClaveSegura2026!', 'password2': 'ClaveSegura2026!',
        }
        data.update(extra or {})
        return self.client.post('/security/registro/', data, follow=True)

    def test_registro_crea_cuenta_cliente_y_deja_logueado(self):
        r = self._post()
        self.assertEqual(r.status_code, 200)
        user = User.objects.get(username='1710034065')  # cédula = usuario
        self.assertTrue(user.check_password('ClaveSegura2026!'))
        self.assertIn('Cliente', [g.name for g in user.groups.all()])
        customer = Customer.objects.get(dni='1710034065')
        self.assertEqual(customer.user, user)
        # queda logueado y aterriza en su portal, no en el dashboard interno
        self.assertEqual(r.redirect_chain[0][0], '/portal/')
        self.assertEqual(len(mail.outbox), 1)
        # La contraseña la eligió el propio cliente: a diferencia de una
        # cuenta creada por el Admin, no debe pedirle cambiarla al entrar.
        self.assertFalse(UserSecurityProfile.objects.filter(user=user).exists())
        r2 = self.client.get('/', follow=True)
        self.assertEqual(r2.redirect_chain[0][0], '/portal/')  # no lo manda a cambiar contraseña

    def test_registro_con_cedula_invalida_es_rechazado(self):
        r = self._post({'dni': '0000000000'})
        self.assertFalse(User.objects.filter(username='0000000000').exists())
        self.assertEqual(len(mail.outbox), 0)

    def test_registro_vincula_a_cliente_ya_existente_sin_cuenta(self):
        # El personal ya lo había registrado antes para facturarle (sin
        # darle acceso al portal): el registro debe vincularse, no duplicar.
        existente = Customer.objects.create(
            dni='1710034065', first_name='Pedro', last_name='Yanez', email='viejo@example.com')
        Invoice.objects.create(customer=existente, total=Decimal('10'))
        self._post()
        existente.refresh_from_db()
        self.assertIsNotNone(existente.user)
        self.assertEqual(Customer.objects.filter(dni='1710034065').count(), 1)  # no se duplicó
        self.assertEqual(existente.invoices.count(), 1)  # su historial se conserva

    def test_registro_con_cedula_ya_vinculada_es_rechazado(self):
        self._post()  # primera cuenta (queda logueado)
        self.client.logout()
        r = self._post({'password1': 'OtraClave2026!', 'password2': 'OtraClave2026!'})
        self.assertIn('Ya existe una cuenta', r.content.decode())
        self.assertEqual(User.objects.filter(username='1710034065').count(), 1)  # no se duplicó

    def test_usuario_autenticado_no_puede_entrar_al_registro(self):
        admin = User.objects.create_superuser('admin_su', 'a@a.com', 'pass12345')
        self.client.force_login(admin)
        r = self.client.get('/security/registro/')
        self.assertEqual(r.status_code, 302)


# =====================================================================
# Roles: pantallas y control de acceso
# =====================================================================
class RolesPantallasTests(TestCase):
    """La consola de roles y el listado de usuarios (con tarjetas por rol)
    solo son accesibles para el Administrador."""
    @classmethod
    def setUpTestData(cls):
        call_command('setup_roles')
        cls.admin = User.objects.create_superuser('admin_roles', 'a@a.com', 'pass12345')
        cls.vendedor = User.objects.create_user('vendedor_roles', password='pass12345')
        cls.vendedor.groups.add(Group.objects.get(name='Vendedor'))

    def test_setup_roles_crea_los_cuatro_roles(self):
        nombres = set(Group.objects.values_list('name', flat=True))
        self.assertTrue({'Administrador', 'Vendedor', 'Analista de Compras', 'Cliente'} <= nombres)

    def test_admin_ve_la_consola_de_roles(self):
        c = Client(); c.force_login(self.admin)
        r = c.get('/security/roles/', follow=True)  # redirige al primer rol
        self.assertEqual(r.status_code, 200)
        self.assertIn('Roles y permisos', r.content.decode())

    def test_admin_ve_usuarios_con_tarjetas_y_filtro_por_rol(self):
        c = Client(); c.force_login(self.admin)
        r = c.get('/security/users/')
        html = r.content.decode()
        self.assertEqual(r.status_code, 200)
        self.assertIn('ur-card', html)          # tarjetas de roles
        self.assertIn('Vendedor', html)
        rol = Group.objects.get(name='Vendedor')
        r = c.get(f'/security/users/?rol={rol.pk}')
        # Filtrado: en las filas de la tabla solo sale el vendedor (el nombre
        # del admin sí aparece en el sidebar como usuario logueado, por eso
        # se compara contra la celda de la tabla y no contra todo el HTML).
        self.assertContains(r, '<div class="cell-primary">vendedor_roles</div>', html=True)
        self.assertNotContains(r, '<div class="cell-primary">admin_roles</div>', html=True)

    def test_no_administrador_no_accede_a_seguridad(self):
        c = Client(); c.force_login(self.vendedor)
        for url in ['/security/users/', '/security/roles/', '/security/users/create/']:
            r = c.get(url)
            self.assertEqual(r.status_code, 302, url)  # lo saca a la página principal


# =====================================================================
# Cambio obligatorio de contraseña temporal (primer login)
# =====================================================================
class ForcePasswordChangeTests(TestCase):
    """El usuario recién creado entra con contraseña temporal y el sistema lo
    obliga a cambiarla antes de usar el resto de la app."""
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user('primer_login', email='p@p.com', password='dyanezg')
        UserSecurityProfile.objects.update_or_create(
            user=self.user, defaults={'must_change_password': True})
        self.client.force_login(self.user)

    def test_middleware_redirige_a_cambiar_contrasena(self):
        r = self.client.get('/')
        self.assertEqual(r.status_code, 302)
        self.assertIn('/security/force-password-change/', r.headers['Location'])

    def test_pantalla_renderiza_con_el_diseno_nuevo(self):
        r = self.client.get('/security/force-password-change/')
        self.assertEqual(r.status_code, 200)
        html = r.content.decode()
        self.assertIn('Crea tu nueva contraseña', html)
        self.assertIn('data-pw-toggle', html)  # botón mostrar/ocultar
        self.assertIn('pwReqs', html)           # checklist de requisitos

    def test_cambiar_contrasena_baja_la_bandera_y_libera_la_app(self):
        r = self.client.post('/security/force-password-change/', {
            'old_password': 'dyanezg',
            'new_password1': 'ClaveNueva2026!',
            'new_password2': 'ClaveNueva2026!',
        }, follow=True)
        self.assertEqual(r.status_code, 200)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('ClaveNueva2026!'))
        self.assertFalse(UserSecurityProfile.objects.get(user=self.user).must_change_password)
        # Ya puede navegar el resto de la app sin ser redirigido.
        self.assertEqual(self.client.get('/').status_code, 200)
