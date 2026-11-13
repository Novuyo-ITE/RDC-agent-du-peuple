import json
from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.core.cache import cache
from django.test import RequestFactory, SimpleTestCase, TestCase
from django.utils import timezone

from .langgraph_router import DRC_ROUTING_GRAPH, web_search_node
from .models import OfficialServiceRegistry
from .official_service_portal import get_official_snapshot
from .services import DRCRagService


class WebDecisionTests(SimpleTestCase):
    def decide(self, query, **kwargs):
        return web_search_node({'query': query, **kwargs})

    def test_news_regulations_prices_and_ambiguous_facts_search_the_web(self):
        for question in ('Quelles sont les dernières actualités ?', 'Combien coûte un passeport ?',
                         'Que dit la loi ?', 'Combien gagnent les soldats ?', 'Explique la photosynthèse.'):
            with self.subTest(question=question):
                self.assertTrue(self.decide(question)['web_search'])

    def test_conversation_text_transforms_and_arithmetic_do_not_search(self):
        for question in ('Bonjour !', 'Mon prénom est Jean.', 'Comment je m’appelle ?',
                         'Résume notre conversation', 'Traduis ce texte : Internet et le passeport', '2 + 2'):
            with self.subTest(question=question):
                decision = self.decide(question)
                self.assertFalse(decision['web_search'])
                self.assertTrue(decision['context_only'])

    def test_explicit_no_web_takes_precedence_over_current_information(self):
        for question in ('Sans internet, quel est le prix actuel du passeport ?',
                         'Ne cherche pas sur internet les nouvelles lois.',
                         'Do not search the web for the latest news.'):
            with self.subTest(question=question):
                self.assertFalse(self.decide(question)['web_search'])
        self.assertTrue(self.decide('Cherche sur internet les informations sur le passeport')['web_search'])
        self.assertFalse(self.decide('Cherche sur internet', internet_allowed=False)['web_search'])
        self.assertFalse(self.decide('Sans internet, mon nom est Jean et quel est le prix du passeport ?')['context_only'])

    def test_followups_and_selected_resource_availability(self):
        history = [{'role': 'user', 'content': 'Je voudrais un passeport.'}]
        self.assertTrue(self.decide('Et le prix ?', history=history)['web_search'])
        self.assertFalse(self.decide('Comment je m’appelle ?', history=history)['web_search'])
        self.assertFalse(self.decide('Résume cet article', context_kind='article', resource_available=True)['web_search'])
        self.assertFalse(self.decide("Résume l’article", context_kind='article', resource_available=True)['web_search'])
        self.assertFalse(self.decide('Que faut-il retenir ?', context_kind='article', resource_available=True)['web_search'])
        self.assertTrue(self.decide('Résume cet article', context_kind='article', resource_available=False)['web_search'])
        self.assertFalse(self.decide('Sans internet, résume cet article', context_kind='article', resource_available=False)['web_search'])

    @patch('apps.rag_engine.services.DRCRagService.answer_query')
    def test_compiled_graph_calls_the_decision_node(self, answer):
        answer.return_value = {'answer': 'Bonjour Jean', 'sources': [], 'fallback_used': False}
        result = DRC_ROUTING_GRAPH.invoke({'query': 'Mon prénom est Jean.', 'history': [], 'user_language': 'fr'})
        self.assertFalse(result['web_search'])
        self.assertTrue(result['context_only'])
        self.assertFalse(answer.call_args.kwargs['web_search'])

    @patch('apps.rag_engine.official_service_portal.requests.get')
    def test_local_snapshot_does_not_open_network_and_can_use_saved_content(self, get):
        cache.clear()
        service = SimpleNamespace(service_code='test-service', official_portal_url='https://example.org', source_snapshot={})
        snapshot = get_official_snapshot(service, allow_network=False)
        self.assertFalse(snapshot['available'])
        get.assert_not_called()
        service.source_snapshot = {'available': True, 'text': 'Texte enregistré'}
        self.assertEqual(get_official_snapshot(service, allow_network=False)['text'], 'Texte enregistré')

    def test_main_chat_streams_without_retrieval_for_conversation(self):
        service = DRCRagService.__new__(DRCRagService)
        service.llm = Mock()
        service.llm.stream.return_value = iter([SimpleNamespace(content='Votre '), SimpleNamespace(content='nom est Jean.')])
        service.retrieve_context = Mock()
        history = [{'role': 'user', 'content': 'Mon prénom est Jean.'}]
        events = list(service.stream_query_events('Comment je m’appelle ?', history=history))
        service.retrieve_context.assert_not_called()
        self.assertEqual([event['token'] for event in events if event['type'] == 'token'], ['Votre ', 'nom est Jean.'])
        self.assertFalse(next(event['web_search_performed'] for event in events if event['type'] == 'sources'))


class OfflineRetrievalTests(TestCase):
    @patch('apps.rag_engine.models.DocumentChunk.objects.exists', return_value=True)
    @patch('apps.rag_engine.services.TavilyDRCSearchTool')
    @patch('apps.rag_engine.official_service_portal.get_official_snapshot')
    def test_local_retrieval_never_calls_web_search_or_fetches_portals(self, snapshot, tavily, chunks_exist):
        OfficialServiceRegistry.objects.create(service_name='Passeport', service_code='passeport',
            institution='Ministère', description='', payment_instructions='', official_portal_url='https://example.org/passport')
        snapshot.return_value = {'available': False, 'facts': {}, 'checked_at': ''}
        service = DRCRagService.__new__(DRCRagService)
        service.generate_query_embedding = Mock()
        result = service.retrieve_context('Prix du passeport', search_web=False)
        tavily.assert_not_called()
        service.generate_query_embedding.assert_not_called()
        self.assertFalse(result['web_search_performed'])
        self.assertFalse(snapshot.call_args.kwargs['allow_network'])


class ContextualChatRoutingTests(SimpleTestCase):
    def setUp(self):
        cache.clear()
        self.factory = RequestFactory()

    def post(self, data):
        return self.factory.post('/', json.dumps(data), content_type='application/json')

    @staticmethod
    def events(response):
        return [json.loads(chunk.decode().removeprefix('data: ').strip()) for chunk in response.streaming_content]

    @patch('apps.rag_engine.source_validation.validate_sources', side_effect=lambda q, sources, model, context='': sources)
    @patch('apps.rag_engine.article_content.fetch_article_body')
    @patch('apps.rag_engine.mcp_tools.TavilyDRCSearchTool')
    @patch('apps.rag_engine.services.get_chat_ollama')
    @patch('django.shortcuts.get_object_or_404')
    @patch('apps.rag_engine.views.ChromaSessionManager')
    def test_article_question_uses_loaded_text_without_web(self, manager, lookup, model, tavily, fetch, validate):
        from .views import article_chat
        lookup.return_value = SimpleNamespace(title='Pont à Goma', source_name='Source',
            source_url='https://example.org/pont', published_at=timezone.now(),
            summary='Résumé.', full_content='Le pont relie deux quartiers.')
        model.return_value.stream.return_value = iter([SimpleNamespace(content='Le pont relie deux quartiers.')])
        events = self.events(article_chat(self.post({'query': 'Résume cet article'}), 7))
        tavily.assert_not_called()
        fetch.assert_not_called()
        self.assertFalse(next(event['web_search_performed'] for event in events if event['type'] == 'sources'))
        self.assertIn('Le pont relie deux quartiers', model.return_value.stream.call_args.args[0][1].content)
        self.assertTrue(any(event['type'] == 'token' for event in events))

    @patch('apps.rag_engine.source_validation.validate_sources', side_effect=lambda q, sources, model, context='': sources)
    @patch('apps.rag_engine.mcp_tools.TavilyDRCSearchTool')
    @patch('apps.rag_engine.official_service_portal.get_official_snapshot')
    @patch('apps.rag_engine.service_browser.current_form_context', return_value={})
    @patch('apps.rag_engine.service_assistance.service_data', return_value={'service': 'Document'})
    @patch('apps.rag_engine.service_assistance.resolve_service')
    @patch('apps.rag_engine.service_assistance.get_chat_ollama')
    @patch('apps.rag_engine.service_assistance.ChromaSessionManager')
    def test_service_question_uses_saved_source_without_web_even_if_enabled(self, manager, model, resolve, record,
                                                                               form, snapshot, tavily, validate):
        from .service_assistance import guide_service
        resolve.return_value = SimpleNamespace(service_name='Document', service_code='document',
            institution='Ministère', official_portal_url='https://example.org/page')
        snapshot.return_value = {'available': True, 'source_url': 'https://example.org/page',
            'text': 'SOURCE: https://example.org/page\nLe document explique les étapes.', 'facts': {}}
        model.return_value.stream.return_value = iter([SimpleNamespace(content='Voici le document.')])
        events = self.events(guide_service(self.post({'query': 'Explique cette source', 'web_search': True}), 'document'))
        tavily.assert_not_called()
        snapshot.assert_called_once()
        self.assertFalse(snapshot.call_args.kwargs['allow_network'])
        context = json.loads(model.return_value.stream.call_args.args[0][1].content)
        self.assertFalse(context['web_search_requested'])
        self.assertIn('Le document explique les étapes', context['selected_source_text_excerpt'])
        self.assertTrue(any(event['type'] == 'token' for event in events))
