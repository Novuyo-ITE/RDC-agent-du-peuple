from datetime import timedelta
from unittest.mock import patch
import json

from django.test import TestCase, SimpleTestCase, RequestFactory
from django.utils import timezone

from apps.rag_engine.chroma_session_manager import session_destination, ChromaSessionManager
from apps.rag_engine.models import OfficialNews


class ArticleDeepLinkTests(TestCase):
    @patch('apps.web_ui.news_refresh.refresh_news_if_due')
    def test_history_link_loads_article_even_if_current_feed_filters_exclude_it(self, refresh):
        article = OfficialNews.objects.create(title='Ancienne actualité à reprendre', slug='article-test',
            source_name='Source officielle', source_url='https://example.com/article', summary='Résumé',
            full_content='Article complet', published_at=timezone.now() - timedelta(days=5))
        response = self.client.get(f'/actualites/?period=today&article={article.pk}&session=article_saved')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['deep_link_article']['id'], str(article.pk))
        self.assertFalse(response.context['news_list'].exists())
        self.assertContains(response, 'deep-link-article-data')


class CommonHistoryMetadataTests(SimpleTestCase):
    def test_article_and_main_chats_have_distinct_resume_destinations(self):
        self.assertEqual(session_destination('article_saved', {'kind': 'article', 'article_id': 7}),
                         '/actualites/?article=7&session=article_saved')
        self.assertEqual(session_destination('sess_saved', {}), '/chat/?session=sess_saved')
        self.assertEqual(session_destination('service_saved', {'kind': 'service', 'service_code': 'passeport'}),
                         '/demarches/passeport/?session=service_saved')

    @patch('apps.rag_engine.views.ChromaSessionManager')
    @patch('apps.rag_engine.service_assistance.resolve_service')
    def test_legacy_service_history_import_resumes_partial_saves_without_duplicates(self, resolve, manager):
        from types import SimpleNamespace
        from apps.rag_engine.views import import_local_conversation
        resolve.return_value = SimpleNamespace(service_code='passeport', service_name='Passeport',
            official_portal_url='https://example.com', institution='Institution')
        manager.return_value.get_session.return_value = {'kind': 'service', 'service_code': 'passeport'}
        manager.return_value.get_session_history.return_value = [{'role': 'user', 'content': 'Question'}]
        manager.return_value.save_message.return_value = True
        request = RequestFactory().post('/', json.dumps({'kind': 'service', 'context_id': 'passeport',
            'session_id': 'service_import', 'messages': [{'role': 'user', 'content': 'Question'},
            {'role': 'assistant', 'content': 'Réponse'}]}), content_type='application/json')
        self.assertEqual(import_local_conversation(request).status_code, 200)
        manager.return_value.save_message.assert_called_once_with('service_import', role='assistant', content='Réponse')
        manager.return_value.save_message.reset_mock()
        manager.return_value.get_session_history.return_value.append({'role': 'assistant', 'content': 'Réponse'})
        self.assertEqual(import_local_conversation(request).status_code, 200)
        manager.return_value.save_message.assert_not_called()
