from django.http import HttpResponse
from django.middleware.csrf import get_token
from django.test import Client, SimpleTestCase, override_settings
from django.urls import path


def csrf_example(request):
    if request.method == 'GET':
        get_token(request)
    return HttpResponse('ok')


urlpatterns = [path('test/', csrf_example)]


@override_settings(ROOT_URLCONF=__name__, ALLOWED_HOSTS=['public.ngrok-free.dev'])
class LocalProxySchemeTests(SimpleTestCase):
    def setUp(self):
        self.client = Client(enforce_csrf_checks=True, HTTP_HOST='public.ngrok-free.dev')
        response = self.client.get('/test/')
        self.csrf_token = response.cookies['csrftoken'].value

    def post(self, **headers):
        return self.client.post('/test/', HTTP_ORIGIN='https://public.ngrok-free.dev',
                                HTTP_X_CSRFTOKEN=self.csrf_token, **headers)

    def test_local_ngrok_https_accepts_matching_origin(self):
        response = self.post(REMOTE_ADDR='127.0.0.1', HTTP_X_FORWARDED_PROTO='http, https')
        self.assertEqual(response.status_code, 200)

    def test_remote_client_cannot_spoof_proxy_scheme(self):
        response = self.post(REMOTE_ADDR='192.0.2.1', HTTP_X_FORWARDED_PROTO='https',
                             HTTP_X_LOCAL_PROXY_SCHEME='https')
        self.assertEqual(response.status_code, 403)

    def test_proxy_does_not_bypass_origin_validation(self):
        response = self.client.post('/test/', REMOTE_ADDR='127.0.0.1',
                                    HTTP_X_FORWARDED_PROTO='https', HTTP_ORIGIN='https://other.example',
                                    HTTP_X_CSRFTOKEN=self.csrf_token)
        self.assertEqual(response.status_code, 403)

    def test_last_forwarded_scheme_controls_trust(self):
        response = self.post(REMOTE_ADDR='127.0.0.1', HTTP_X_FORWARDED_PROTO='https, http')
        self.assertEqual(response.status_code, 403)
