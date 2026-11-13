from types import SimpleNamespace
from unittest.mock import patch

from bs4 import BeautifulSoup
from django.core.cache import caches
from django.test import SimpleTestCase

from apps.rag_engine.models import OfficialServiceRegistry
from apps.rag_engine.official_service_portal import get_official_snapshot, read_pdf_source, read_search_source


class SourceReaderTests(SimpleTestCase):
    def test_html_source_keeps_actual_content_without_procedure_fields(self):
        response = SimpleNamespace(headers={'Content-Type': 'text/html'}, encoding='utf-8',
            url='https://example.gouv.cd/report',
            content=b'<html>', text='<nav>Menu</nav><main><h1>Programme de droit</h1><p>Cours de droit civil.</p></main>')
        result = read_search_source(response)
        self.assertEqual(result['format'], 'html')
        self.assertIn('Cours de droit civil.', result['sections'][0]['text'])
        self.assertNotIn('Menu', result['sections'][0]['text'])
        self.assertNotIn('fees', result)

    @patch('pypdf.PdfReader')
    def test_pdf_preserves_page_citations_and_reports_partial_reading(self, reader):
        reader.return_value.pages = [SimpleNamespace(extract_text=lambda: 'Texte du programme.')] * 501
        result = read_pdf_source(b'%PDF-test', 'https://example.gouv.cd/report.pdf')
        self.assertEqual(result['page_count'], 501)
        self.assertEqual(len(result['sections']), 500)
        self.assertTrue(result['truncated'])
        self.assertEqual(result['sections'][1]['url'], 'https://example.gouv.cd/report.pdf#page=2')

    @patch('apps.rag_engine.official_service_portal.extract_supported_facts')
    @patch('apps.rag_engine.official_service_portal.requests.get')
    @patch('apps.rag_engine.official_service_portal.cache')
    def test_search_source_does_not_force_procedural_extraction(self, cache, request, extract):
        request.return_value = SimpleNamespace(headers={'Content-Type': 'text/html'}, encoding='utf-8',
            url='https://example.gouv.cd/report', content=b'<html>',
            text='<main><h1>Document officiel</h1><p>Informations du document.</p></main>',
            raise_for_status=lambda: None)
        service = OfficialServiceRegistry(service_code='site-test', service_name='Document',
            official_portal_url='https://example.gouv.cd/report')
        result = get_official_snapshot(service, force_refresh=True)
        self.assertTrue(result['available'])
        self.assertIn('Informations du document.', result['source_content']['sections'][0]['text'])
        extract.assert_not_called()

    @patch('apps.rag_engine.official_service_portal.requests.get')
    @patch('apps.rag_engine.official_service_portal.cache')
    def test_invalid_pdf_remains_unavailable_instead_of_fabricating_content(self, cache, request):
        request.return_value = SimpleNamespace(headers={'Content-Type': 'application/pdf'},
            url='https://example.gouv.cd/report.pdf', content=b'%PDF-broken',
            raise_for_status=lambda: None)
        service = OfficialServiceRegistry(service_code='site-broken', service_name='Document',
            official_portal_url='https://example.gouv.cd/report.pdf')
        result = get_official_snapshot(service, force_refresh=True)
        self.assertFalse(result['available'])
        self.assertEqual(result['text'], '')

    def test_search_result_has_reader_and_hides_administrative_template(self):
        code = 'site-reader-template'
        caches['service_sources'].set(code, {'title': 'Programme de droit',
                                           'url': 'https://example.gouv.cd/report.pdf'})
        self.addCleanup(caches['service_sources'].delete, code)
        response = self.client.get('/demarches/' + code + '/')
        self.assertEqual(response.status_code, 200)
        soup = BeautifulSoup(response.content, 'html.parser')
        self.assertIsNotNone(soup.select_one('#source-reader-content'))
        self.assertTrue(soup.find('section', attrs={'aria-label': 'Démarche et formulaire'}).has_attr('hidden'))
        self.assertIn('Comprendre cette source', soup.get_text())
