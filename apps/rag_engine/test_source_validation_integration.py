import json
from types import SimpleNamespace
from unittest.mock import patch

from django.core.cache import cache
from django.test import RequestFactory, SimpleTestCase
from django.utils import timezone

from .service_assistance import guide_service
from .views import article_chat


class SourceValidationIntegrationTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()
        cache.clear()

    def post(self, data):
        return self.factory.post('/', json.dumps(data), content_type='application/json')

    @staticmethod
    def events(response):
        return [json.loads(chunk.decode().removeprefix('data: ').strip()) for chunk in response.streaming_content]

    @patch('apps.rag_engine.views.ChromaSessionManager')
    @patch('apps.rag_engine.mcp_tools.TavilyDRCSearchTool')
    @patch('apps.rag_engine.services.get_chat_ollama')
    @patch('django.shortcuts.get_object_or_404')
    def test_news_chat_only_passes_reviewed_sources_to_the_model(self, lookup, get_model, search, manager):
        lookup.return_value = SimpleNamespace(title='Pont à Goma', source_name='Source',
            source_url='https://example.org/pont', published_at=timezone.now(),
            summary='Annonce du pont', full_content='Le pont relie deux quartiers.')
        search.return_value.search.return_value = {'structured': [
            {'title': 'Football', 'url': 'https://example.org/sport', 'snippet': 'Un match de football.'}]}
        model = get_model.return_value
        model.bind.return_value.invoke.return_value.content = '{"relevant_ids": [0]}'
        model.stream.return_value = iter([SimpleNamespace(content='Voir https://example.org/pont et https://example.org/sport')])
        events = self.events(article_chat(self.post({'query': 'Que change le pont ?'}), 7))
        sources = next(event['sources'] for event in events if event['type'] == 'sources')
        self.assertEqual([source['url'] for source in sources], ['https://example.org/pont'])
        self.assertNotIn('_content', sources[0])
        prompt = model.stream.call_args.args[0]
        self.assertNotIn('Un match de football', prompt[2].content)
        answer = ''.join(event['token'] for event in events if event['type'] == 'token')
        self.assertIn('https://example.org/pont', answer)
        self.assertNotIn('https://example.org/sport', answer)

    @patch('apps.rag_engine.service_assistance.ChromaSessionManager')
    @patch('apps.rag_engine.service_browser.current_form_context', return_value={})
    @patch('apps.rag_engine.mcp_tools.TavilyDRCSearchTool')
    @patch('apps.rag_engine.official_service_portal.get_official_snapshot')
    @patch('apps.rag_engine.service_assistance.service_data', return_value={'service': 'Passeport'})
    @patch('apps.rag_engine.service_assistance.resolve_service')
    @patch('apps.rag_engine.service_assistance.get_chat_ollama')
    def test_service_chat_filters_unrelated_results_and_keeps_selected_page(self, get_model, resolve, record,
                                                                           snapshot, search, form, manager):
        resolve.return_value = SimpleNamespace(service_name='Passeport', service_code='passeport',
            institution='Ministère', official_portal_url='https://example.org/passeport')
        snapshot.return_value = {'available': True, 'source_url': 'https://example.org/passeport',
            'text': 'SOURCE: https://example.org/passeport\nFrais : 50 dollars.',
            'facts': {'fees': {'url': 'https://example.org/passeport', 'text': 'Frais : 50 dollars.'}}}
        search.return_value.search.return_value = {'structured': [
            {'title': 'Sport', 'url': 'https://example.org/sport', 'snippet': 'Un match de football.'}]}
        model = get_model.return_value
        model.bind.return_value.invoke.return_value.content = '{"relevant_ids": [0]}'
        model.stream.return_value = iter([SimpleNamespace(content='Frais : 50 dollars.')])
        events = self.events(guide_service(self.post({'query': 'Combien coûte le passeport ?', 'web_search': True}), 'passeport'))
        sources = next(event['sources'] for event in events if event['type'] == 'sources')
        self.assertEqual([source['url'] for source in sources], ['https://example.org/passeport'])
        prompt = model.stream.call_args.args[0]
        self.assertIn('Frais : 50 dollars.', prompt[1].content)
        self.assertNotIn('Un match de football', prompt[1].content)
