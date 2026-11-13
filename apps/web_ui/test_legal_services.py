from io import StringIO
from unittest.mock import patch
from types import SimpleNamespace

from django.core.management import call_command
from django.test import TestCase, SimpleTestCase

from apps.rag_engine.models import OfficialServiceRegistry
from apps.rag_engine.management.commands.seed_legal_services import LEGAL_SERVICES


class LegalServiceCatalogTests(TestCase):
    def test_seed_is_repeatable_and_preserves_reviewed_data(self):
        call_command('seed_legal_services', stdout=StringIO())
        service = OfficialServiceRegistry.objects.get(service_code=LEGAL_SERVICES[0]['service_code'])
        service.description = 'Reviewed description'
        service.save()
        call_command('seed_legal_services', stdout=StringIO())
        self.assertEqual(OfficialServiceRegistry.objects.count(), 3)
        service.refresh_from_db()
        self.assertEqual(service.description, 'Reviewed description')
        for service in OfficialServiceRegistry.objects.all():
            self.assertEqual(service.category, 'justice')
            self.assertIsNone(service.processing_time_days)
            self.assertIsNone(service.official_cost_usd)
            self.assertIsNone(service.official_cost_cdf)
            self.assertTrue(service.official_portal_url.startswith('https://servicepublic.gouv.cd/service/'))

    def test_legal_category_and_search_show_new_services(self):
        call_command('seed_legal_services', stdout=StringIO())
        response = self.client.get('/demarches/?category=justice')
        self.assertEqual(len(response.context['services']), 3)
        self.assertContains(response, 'data-lucide="scale"', count=3)
        response = self.client.get('/demarches/?q=casier')
        self.assertEqual(len(response.context['services']), 1)
        self.assertContains(response, 'Extrait de casier judiciaire')


class LegalSourceAccessTests(SimpleTestCase):
    @patch('apps.rag_engine.official_service_portal.cache')
    @patch('apps.rag_engine.official_service_portal.requests.get')
    def test_login_page_is_not_treated_as_service_instructions(self, request, cache):
        from apps.rag_engine.official_service_portal import get_official_snapshot
        request.return_value = SimpleNamespace(
            url='https://servicepublic.gouv.cd/login', raise_for_status=lambda: None)
        service = OfficialServiceRegistry(**LEGAL_SERVICES[0])
        result = get_official_snapshot(service, force_refresh=True)
        self.assertFalse(result['available'])
        self.assertEqual(result['text'], '')
