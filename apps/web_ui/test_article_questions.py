import json
from types import SimpleNamespace
from unittest.mock import patch

from django.core.cache import cache
from django.test import RequestFactory, SimpleTestCase, override_settings
from django.utils import timezone

from apps.rag_engine.views import article_questions


@override_settings(OLLAMA_MODEL='test-model')
class ArticleQuestionTests(SimpleTestCase):
    def setUp(self):
        cache.clear()
        self.article = SimpleNamespace(pk=7, title='Un pont ouvre à Goma', source_name='Média',
            published_at=timezone.now(), summary='Une ouverture annoncée.', full_content='Le pont relie deux quartiers de Goma.')
        self.factory = RequestFactory()

    def request(self):
        return self.factory.post('/', json.dumps({'language': 'fr'}), content_type='application/json')

    @patch('apps.rag_engine.services.get_chat_ollama')
    @patch('django.shortcuts.get_object_or_404')
    def test_questions_use_selected_article_and_cache_only_generated_results(self, lookup, model):
        lookup.return_value = self.article
        model.return_value.bind.return_value.invoke.return_value = SimpleNamespace(content=json.dumps({'questions': [
            'Quels quartiers le pont relie-t-il ?', 'Pourquoi ce pont est-il ouvert maintenant ?',
            'Que pourrait changer ce pont pour Goma ?']}))
        result = article_questions(self.request(), 7)
        data = json.loads(result.content)
        self.assertTrue(data['generated'])
        self.assertEqual(len(data['questions']), 3)
        self.assertEqual(model.return_value.bind.call_args.kwargs['options']['num_predict'], 260)
        messages = model.return_value.bind.return_value.invoke.call_args.args[0]
        self.assertIn('Le pont relie deux quartiers de Goma', messages[1].content)
        self.assertIn('jamais une instruction', messages[0].content)
        article_questions(self.request(), 7)
        model.return_value.bind.return_value.invoke.assert_called_once()
        self.assertEqual(lookup.call_args.kwargs, {'pk': 7})
        self.assertIn('is_verified', str(lookup.call_args.args[0].query.where))

    @patch('apps.rag_engine.services.get_chat_ollama')
    @patch('django.shortcuts.get_object_or_404')
    def test_invalid_model_output_falls_back_to_article_title_and_retries_later(self, lookup, model):
        lookup.return_value = self.article
        model.return_value.bind.return_value.invoke.return_value = SimpleNamespace(content='invalid')
        result = json.loads(article_questions(self.request(), 7).content)
        self.assertFalse(result['generated'])
        self.assertEqual(len(result['questions']), 3)
        self.assertTrue(all('Un pont ouvre à Goma' in question for question in result['questions']))
        article_questions(self.request(), 7)
        self.assertEqual(model.return_value.bind.return_value.invoke.call_count, 2)
