import json
from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.test import SimpleTestCase, RequestFactory, Client
from .service_browser import official_browser_action, public_host


class IntegratedPortalTests(SimpleTestCase):
    def service(self):
        return SimpleNamespace(service_code='test-service', service_name='Test service',
            official_portal_url='https://official.example/form', source_snapshot={
                'form_resources': [{'url': 'https://official.example/form', 'title': 'Application'}]})

    @patch('apps.rag_engine.service_browser._browser.execute')
    @patch('apps.rag_engine.service_assistance.resolve_service')
    def test_portal_session_is_bound_to_the_citizens_django_session(self, resolve, execute):
        resolve.return_value = self.service()
        execute.return_value = {'active': True, 'fields': [], 'buttons': []}
        owners = []
        for session in ({}, {}):
            request = RequestFactory().post('/', json.dumps({'action': 'start', 'url': 'https://official.example/form'}), content_type='application/json')
            request.session = session
            response = official_browser_action(request, 'test-service')
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response['Cache-Control'], 'no-store')
            owners.append(execute.call_args.args[0])
            self.assertEqual(session['official_browser_owner'], owners[-1])
        self.assertNotEqual(*owners)

    @patch('apps.rag_engine.service_browser._browser.execute')
    def test_csrf_is_required_before_any_portal_action(self, execute):
        response = Client(enforce_csrf_checks=True).post('/api/rag/services/test-service/browser/',
            data=json.dumps({'action': 'button', 'button': 'submit'}), content_type='application/json')
        self.assertEqual(response.status_code, 403)
        execute.assert_not_called()

    @patch('apps.rag_engine.service_browser.socket.getaddrinfo')
    def test_private_and_loopback_networks_are_not_allowed(self, resolve):
        for address in ('127.0.0.1', '10.0.0.1', '169.254.169.254', '::1'):
            resolve.return_value = [(None, None, None, None, (address, 443))]
            self.assertFalse(public_host('example.test'))

    @patch('apps.rag_engine.service_assistance.get_chat_ollama')
    @patch('apps.rag_engine.service_assistance.resolve_service')
    @patch('apps.rag_engine.official_service_portal.get_official_snapshot', return_value={'forms': []})
    @patch('apps.rag_engine.service_browser.current_form_context')
    def test_ai_can_prepare_actual_live_fields_without_a_preloaded_form(self, context, snapshot, resolve, model):
        from .service_assistance import prepare_official_form
        resolve.return_value = self.service()
        context.return_value = {'source_url': 'https://official.example/form', 'fields': [
            {'name': 'field-current-ref', 'source_name': 'applicant_name', 'label': 'Nom', 'type': 'text'}]}
        model.return_value.bind.return_value.invoke.return_value.content = json.dumps({'suggestions': {
            'field-current-ref': 'Jean', 'invented-field': 'value'}})
        request = RequestFactory().post('/', json.dumps({'use_live_form': True, 'values': {'applicant': 'Jean'}}), content_type='application/json')
        response = prepare_official_form(request, 'test-service')
        self.assertEqual(json.loads(response.content)['suggestions'], {'field-current-ref': 'Jean'})
