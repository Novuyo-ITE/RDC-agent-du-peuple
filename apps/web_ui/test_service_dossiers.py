import json
from io import StringIO
from bs4 import BeautifulSoup

from django.conf import settings
from django.core.cache import cache
from django.core.management import call_command
from django.test import TestCase

from apps.rag_engine.models import OfficialServiceRegistry
from apps.rag_engine.official_service_portal import get_official_snapshot


class ResearchedDossierTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.dossiers = json.loads((settings.BASE_DIR / 'apps/rag_engine/data/service_dossiers.json').read_text(encoding='utf-8'))
        for code in cls.dossiers:
            OfficialServiceRegistry.objects.create(service_code=code, service_name=code,
                institution='Official institution', official_portal_url='https://example.com')
        call_command('load_service_dossiers', stdout=StringIO())

    def test_all_eight_dossiers_survive_cache_clear_and_have_sources_and_form_routes(self):
        cache.clear()
        self.assertEqual(len(self.dossiers), 8)
        for service in OfficialServiceRegistry.objects.all():
            with self.subTest(service=service.service_code):
                snapshot = get_official_snapshot(service)
                self.assertEqual(snapshot['provenance'], 'reviewed_official_sources')
                self.assertGreaterEqual(len(snapshot['facts']['steps']), 5)
                self.assertTrue(snapshot['facts']['documents'])
                self.assertTrue(snapshot['form_resources'])
                for value in snapshot['facts'].values():
                    for fact in value if isinstance(value, list) else [value]:
                        self.assertIn(fact['url'], snapshot['references'])

    def test_every_workspace_renders_real_information_before_javascript_or_model(self):
        for service in OfficialServiceRegistry.objects.all():
            with self.subTest(service=service.service_code):
                response = self.client.get('/demarches/' + service.service_code + '/')
                self.assertEqual(response.status_code, 200)
                snapshot = service.source_snapshot
                self.assertContains(response, snapshot['facts']['description']['text'])
                soup = BeautifulSoup(response.content, 'html.parser')
                for stage in ('prepare', 'apply'):
                    self.assertIn(snapshot['form_resources'][0]['title'], soup.select_one('#step-' + stage).get_text())
                self.assertContains(response, 'service-initial-snapshot')
                self.assertNotContains(response, 'Aucune procédure préchargée')

    def test_form_drafts_only_expose_inspected_public_fields(self):
        services_with_fields = []
        for service in OfficialServiceRegistry.objects.all():
            for form in service.source_snapshot['forms']:
                services_with_fields.append(service.service_code)
                self.assertTrue(form['requires_official_site'])
                for field in form['fields']:
                    self.assertNotIn(field['type'], ['password', 'hidden', 'file', 'checkbox'])
        self.assertEqual(len(services_with_fields), 2)

    def test_import_does_not_relabel_historical_review_as_today(self):
        before = OfficialServiceRegistry.objects.first().source_snapshot['checked_at']
        call_command('load_service_dossiers', stdout=StringIO())
        self.assertEqual(OfficialServiceRegistry.objects.first().source_snapshot['checked_at'], before)
