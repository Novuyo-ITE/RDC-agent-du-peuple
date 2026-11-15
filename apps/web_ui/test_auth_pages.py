from django.test import TestCase
from django.contrib.auth import get_user_model


class AuthPageTests(TestCase):
    def test_standalone_forms_render_without_workspace(self):
        for path in ['/login/', '/register/']:
            response = self.client.get(path)
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, 'css/auth.css')
            self.assertContains(response, 'csrfmiddlewaretoken')
            self.assertNotContains(response, 'id="main-sidebar"')

    def test_invalid_registration_retains_username_and_shows_errors(self):
        response = self.client.post('/register/', {'username': 'citoyen', 'password1': 'short', 'password2': 'different'})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'value="citoyen"')
        self.assertContains(response, 'aria-invalid="true"')
        self.assertNotContains(response, 'value="short"')

    def test_login_authenticates_and_preserves_destination(self):
        get_user_model().objects.create_user(username='citoyen', password='UnMotDePasseSolide!2026')
        response = self.client.post('/login/', {'username': 'citoyen', 'password': 'UnMotDePasseSolide!2026', 'next': '/chat/'})
        self.assertRedirects(response, '/chat/', fetch_redirect_response=False)
        self.assertIn('_auth_user_id', self.client.session)
