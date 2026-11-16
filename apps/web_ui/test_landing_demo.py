from types import SimpleNamespace
from unittest.mock import patch
from django.test import SimpleTestCase
from .landing_demo import landing_service_examples


class LandingDemoTests(SimpleTestCase):
    @patch('apps.web_ui.landing_demo.OfficialServiceRegistry.objects.filter')
    def test_copies_full_sourced_sequence_without_inventing_steps(self, query):
        steps = [{'text': 'Etape officielle A', 'url': 'https://diplomatie.gouv.cd/faq'},
                 {'text': 'Etape officielle B', 'url': 'https://passeport.gouv.cd/'}]
        query.return_value.only.return_value = [SimpleNamespace(
            service_code='passeport-biometrique-ordinaire', source_snapshot={'facts': {'steps': steps}})]
        result = landing_service_examples()
        self.assertEqual(len(result), 1)
        self.assertTrue(result[0]['answer'].endswith('1. Etape officielle A\n\n2. Etape officielle B'))
        self.assertEqual(result[0]['sources'], [step['url'] for step in steps])
        self.assertIn('/demarches/', result[0]['href'])

    @patch('apps.web_ui.landing_demo.OfficialServiceRegistry.objects.filter')
    def test_missing_or_unsourced_steps_do_not_get_demo_procedures(self, query):
        query.return_value.only.return_value = [
            SimpleNamespace(service_code='passeport-biometrique-ordinaire', source_snapshot={}),
            SimpleNamespace(service_code='creation-entreprise-guce', source_snapshot={'facts': {'steps': [
                {'text': 'Unsupported', 'url': 'javascript:alert(1)'}]}})]
        self.assertEqual(landing_service_examples(), [])
