"""Suite de tests de security: recuperación de contraseña por correo
(usa las vistas incluidas de django.contrib.auth, con plantillas propias).

Corre con: python manage.py test security
"""
import re

from django.contrib.auth.models import User
from django.core import mail
from django.test import Client, TestCase


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
