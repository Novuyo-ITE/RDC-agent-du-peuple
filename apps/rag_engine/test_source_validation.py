import json
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.test import SimpleTestCase
from django.utils import timezone

from .services import DRCRagService
from .source_validation import public_sources, reviewed_snapshot, validate_sources


class SourceValidationTests(SimpleTestCase):
    def setUp(self):
        self.model = Mock()
        self.sources = [
            {'title': 'Passeport', 'url': 'https://example.cd/passport',
             'excerpt': 'Le passeport coûte 50 dollars.', '_content': 'Le passeport coûte 50 dollars.'},
            {'title': 'Sport', 'url': 'https://example.cd/sport',
             'excerpt': 'Une équipe gagne un match.', '_content': 'Une équipe gagne un match.'},
            {'title': 'Page sans texte', 'url': 'https://example.cd/empty'},
        ]

    def response(self, payload):
        self.model.bind.return_value.invoke.return_value = SimpleNamespace(content=json.dumps(payload))

    def test_reviewer_selects_only_existing_evidence_and_deduplicates_ids(self):
        self.response({'relevant_ids': [0, 0, 4, True, '1']})
        selected = validate_sources('Quel est le prix du passeport ?', self.sources, self.model)
        self.assertEqual([source['url'] for source in selected], ['https://example.cd/passport'])
        messages = self.model.bind.return_value.invoke.call_args.args[0]
        payload = json.loads(messages[1].content)
        self.assertEqual(len(payload['sources']), 2)
        self.assertIn('50 dollars', payload['sources'][0]['passage'])
        self.assertNotIn('_content', public_sources(selected)[0])

    def test_invalid_or_unavailable_review_never_returns_unreviewed_sources(self):
        self.response({'wrong_key': [0, 1]})
        self.assertEqual(validate_sources('Question', self.sources, self.model), [])
        self.model.bind.return_value.invoke.side_effect = RuntimeError('offline')
        self.assertEqual(validate_sources('Question', self.sources, self.model), [])

    def test_general_news_falls_back_only_to_recent_readable_approved_articles(self):
        now = timezone.now()
        recent = {'url': 'https://example.cd/recent', 'title': 'Nouvelle à Kinshasa',
                  '_content': 'Un événement est rapporté à Kinshasa.', 'source_kind': 'news',
                  'published_at': (now - timedelta(hours=2)).isoformat()}
        old = {**recent, 'url': 'https://example.cd/old', 'published_at': (now - timedelta(days=20)).isoformat()}
        future = {**recent, 'url': 'https://example.cd/future', 'published_at': (now + timedelta(days=1)).isoformat()}
        social = {**recent, 'url': 'https://example.cd/social', 'source_kind': 'social'}
        empty = {**recent, 'url': 'https://example.cd/empty', '_content': ''}
        foreign = {**recent, 'url': 'https://example.cd/foreign', 'title': 'Sport en France',
                   '_content': 'Un match à Paris.'}
        self.response({})
        candidates = [recent, old, future, social, empty, foreign]
        selected = validate_sources('quelles sont les nouvelles?', candidates, self.model)
        self.assertEqual([item['url'] for item in selected], [recent['url']])
        self.assertEqual(selected[0]['relevance_method'], 'recent_approved_news')
        self.assertEqual(validate_sources('Quelles nouvelles sur la santé ?', candidates, self.model), [])
        self.assertEqual(validate_sources('Quelles nouvelles dans le monde ?', candidates, self.model), [])
        self.response({'relevant_ids': []})
        self.assertEqual([item['url'] for item in validate_sources('quelles sont les nouvelles?', candidates, self.model)], [recent['url']])

    def test_reviewer_requests_a_schema_with_the_required_id_list(self):
        self.response({'relevant_ids': [0]})
        validate_sources('Quel est le prix ?', self.sources, self.model)
        schema = self.model.bind.call_args.kwargs['format']
        self.assertEqual(schema['required'], ['relevant_ids'])

    def test_snapshot_restricts_facts_and_page_text_to_reviewed_sources(self):
        snapshot = {'available': True, 'facts': {'fees': {'url': self.sources[0]['url'], 'text': '50'},
                    'documents': [{'url': self.sources[1]['url'], 'text': 'Unrelated'}]},
                    'source_content': {'sections': [{'url': self.sources[1]['url'], 'text': 'Other'}]}}
        result = reviewed_snapshot(snapshot, self.sources[:1], {
            self.sources[0]['url']: 'Passeport 50 dollars', self.sources[1]['url']: 'Unrelated'})
        self.assertEqual(result['facts']['fees']['text'], '50')
        self.assertEqual(result['facts']['documents'], [])
        self.assertEqual(result['source_content']['sections'], [])
        self.assertNotIn('Unrelated', result['text'])

    @patch('apps.rag_engine.langgraph_router.classify_query_intent', return_value='research_needed')
    def test_main_chat_streams_only_reviewed_evidence_and_urls(self, classify):
        self.response({'relevant_ids': [0]})
        self.model.stream.return_value = iter([SimpleNamespace(content='Voici le prix : https://example.cd/passport')])
        service = DRCRagService.__new__(DRCRagService)
        service.llm = self.model
        service.retrieve_context = Mock(return_value={'context_text': 'UNFILTERED',
            'sources': self.sources, 'fallback_used': True})
        events = list(service.stream_query_events('Quel est le prix du passeport ?', history=[]))
        sources = next(event['sources'] for event in events if event['type'] == 'sources')
        self.assertEqual([source['url'] for source in sources], ['https://example.cd/passport'])
        self.assertNotIn('_content', sources[0])
        prompt = self.model.stream.call_args.args[0][0].content
        self.assertIn('50 dollars', prompt)
        self.assertNotIn('équipe gagne', prompt)
        self.assertNotIn('UNFILTERED', prompt)
        self.assertEqual([source['url'] for source in events[-1]['sources']], ['https://example.cd/passport'])

    @patch('apps.rag_engine.langgraph_router.classify_query_intent', return_value='research_needed')
    def test_main_chat_withholds_sources_and_retrieved_text_when_review_fails(self, classify):
        self.model.bind.return_value.invoke.side_effect = RuntimeError('offline')
        self.model.stream.return_value = iter([SimpleNamespace(content='Je ne peux pas vérifier ce prix.')])
        service = DRCRagService.__new__(DRCRagService)
        service.llm = self.model
        service.retrieve_context = Mock(return_value={'context_text': 'UNFILTERED',
            'sources': self.sources, 'fallback_used': True})
        events = list(service.stream_query_events('Quel est le prix ?', history=[]))
        sources = next(event['sources'] for event in events if event['type'] == 'sources')
        self.assertEqual(sources, [])
        prompt = self.model.stream.call_args.args[0][0].content
        self.assertNotIn('UNFILTERED', prompt)
        self.assertNotIn('50 dollars', prompt)
        self.assertIn('Aucune source pertinente', prompt)

    def test_general_news_resolves_numbered_citations_in_the_model_source_order(self):
        now = timezone.now()
        older = {'url': 'https://example.cd/older', 'title': 'Article ancien', 'source_kind': 'news',
                 '_content': 'Ancienne nouvelle en RDC.', 'published_at': (now - timedelta(days=1)).isoformat()}
        newer = {'url': 'https://example.cd/newer', 'title': 'Article récent', 'source_kind': 'news',
                 '_content': 'Nouvelle récente en RDC.', 'published_at': now.isoformat()}
        self.response({'relevant_ids': [0, 1]})
        self.model.stream.return_value = iter([SimpleNamespace(content='Nouvelles : [SOU'),
                                               SimpleNamespace(content='RCE 1].')])
        service = DRCRagService.__new__(DRCRagService)
        service.llm = self.model
        service.retrieve_context = Mock(return_value={'context_text': '', 'sources': [older, newer], 'fallback_used': False})
        events = list(service.stream_query_events('quelles sont les nouvelles?', history=[]))
        answer = ''.join(event['token'] for event in events if event['type'] == 'token')
        self.assertIn('[Source 1](https://example.cd/newer)', answer)
        self.assertEqual(events[-1]['sources'][0]['url'], newer['url'])
