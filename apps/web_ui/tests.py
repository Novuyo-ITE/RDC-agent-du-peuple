from unittest.mock import patch

from django.test import SimpleTestCase

from . import news_refresh


class ArticleChatTests(SimpleTestCase):
    def setUp(self):
        reviewer = patch('apps.rag_engine.source_validation.validate_sources',
                         side_effect=lambda question, sources, model, context='': sources)
        reviewer.start()
        self.addCleanup(reviewer.stop)
        manager = patch('apps.rag_engine.views.ChromaSessionManager')
        self.history_manager = manager.start().return_value
        self.history_manager.get_session.return_value = None
        self.history_manager.get_session_history.return_value = []
        self.history_manager.save_message.return_value = True
        self.addCleanup(manager.stop)

    def test_article_extraction_keeps_entire_body_and_excludes_navigation(self):
        from apps.rag_engine.article_content import extract_article_body

        paragraph = 'Detailed article paragraph with facts. ' * 100
        html = f'<nav>Menu links</nav><article><div class="entry-content"><p>{paragraph}</p><p>Final paragraph.</p></div><aside>Related stories</aside></article>'
        body = extract_article_body(html)
        self.assertGreater(len(body), 2000)
        self.assertIn('Final paragraph.', body)
        self.assertNotIn('Menu links', body)
        self.assertNotIn('Related stories', body)

    @patch('apps.rag_engine.services.get_chat_ollama')
    @patch('django.shortcuts.get_object_or_404')
    @patch('apps.rag_engine.mcp_tools.TavilyDRCSearchTool')
    def test_selected_article_and_follow_up_reach_local_model(self, search, lookup, model):
        import json
        from types import SimpleNamespace
        from django.test import RequestFactory
        from django.utils import timezone
        from apps.rag_engine.views import article_chat

        lookup.return_value = SimpleNamespace(title='Selected news', source_name='Radio',
            source_url='https://example.com/article', published_at=timezone.now(),
            summary='Article summary', full_content='Details only in this article')
        search.return_value.search.return_value = {'structured': [
            {'title': 'New development', 'url': 'https://example.com/update', 'snippet': 'Recent details'}]}
        model.return_value.stream.return_value = iter([
            SimpleNamespace(content='An '), SimpleNamespace(content='answer')])
        request = RequestFactory().post('/api/rag/articles/7/chat/', data=json.dumps({
            'query': 'Why?', 'language': 'en',
            'history': [{'role': 'user', 'content': 'Summarize it'},
                        {'role': 'assistant', 'content': 'Earlier explanation'}],
        }), content_type='application/json')
        response = article_chat(request, 7)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['X-Accel-Buffering'], 'no')
        self.assertIn('no-transform', response['Cache-Control'])
        events = [json.loads(chunk.decode().removeprefix('data: ').strip()) for chunk in response.streaming_content]
        self.assertEqual([e['token'] for e in events if e['type'] == 'token'], ['An ', 'answer'])
        self.assertEqual(events[-1]['type'], 'done')
        self.assertTrue(events[-1]['history_saved'])
        sid = events[-1]['session_id']
        self.assertTrue(sid.startswith('article_'))
        self.history_manager.get_or_create_session.assert_called_once_with(sid, title='Actualité · Selected news',
            context={'kind': 'article', 'article_id': 7, 'article_title': 'Selected news'})
        calls = self.history_manager.save_message.call_args_list
        self.assertEqual([(c.kwargs['role'], c.kwargs['content']) for c in calls[-2:]],
                         [('user', 'Why?'), ('assistant', 'An answer')])
        self.assertEqual(events[-1]['sources'][-1]['url'], 'https://example.com/update')
        messages = model.return_value.stream.call_args.args[0]
        self.assertIn('Details only in this article', messages[1].content)
        self.assertIn('Recent details', messages[2].content)
        self.assertEqual(messages[-2].content, 'Earlier explanation')
        self.assertEqual(messages[-1].content, 'Why?')
        self.assertIn('English', messages[0].content)
        self.assertIn('Separate reported facts, attributed claims and your analysis', messages[0].content)
        self.assertIn('practical implications', messages[0].content)
        self.assertEqual(lookup.call_args.kwargs, {'pk': 7})
        self.assertIn('is_verified', str(lookup.call_args.args[0].query.where))
        self.assertEqual(events[1]['type'], 'status')
        self.assertEqual(events[-1]['sources'][0]['excerpt'], 'Details only in this article')

    @patch('apps.rag_engine.services.get_chat_ollama')
    @patch('django.shortcuts.get_object_or_404')
    @patch('apps.rag_engine.mcp_tools.TavilyDRCSearchTool')
    def test_article_follow_up_uses_persisted_conversation_and_cannot_change_article(self, search, lookup, model):
        import json
        from types import SimpleNamespace
        from django.test import RequestFactory
        from django.utils import timezone
        from apps.rag_engine.views import article_chat
        lookup.return_value = SimpleNamespace(title='Article', source_name='Source', source_url='https://example.com',
            published_at=timezone.now(), summary='Summary', full_content='Body')
        self.history_manager.get_session.return_value = {'kind': 'article', 'article_id': 7}
        self.history_manager.get_session_history.return_value = [
            {'role': 'user', 'content': 'Question sauvegardée'}, {'role': 'assistant', 'content': 'Réponse sauvegardée'}]
        search.return_value.search.return_value = {'structured': []}
        model.return_value.stream.return_value = iter([SimpleNamespace(content='Suite')])
        request = RequestFactory().post('/', json.dumps({'query': 'Continue', 'session_id': 'article_saved',
            'history': [{'role': 'user', 'content': 'Historique client remplacé'}]}), content_type='application/json')
        response = article_chat(request, 7)
        list(response.streaming_content)
        prompt = model.return_value.stream.call_args.args[0]
        self.assertIn('Question sauvegardée', [message.content for message in prompt])
        self.assertNotIn('Historique client remplacé', [message.content for message in prompt])
        self.assertEqual(article_chat(request, 8).status_code, 409)

    @patch('apps.rag_engine.services.get_chat_ollama')
    @patch('django.shortcuts.get_object_or_404')
    @patch('apps.rag_engine.mcp_tools.TavilyDRCSearchTool')
    def test_search_failure_still_streams_and_model_failure_is_explicit(self, search, lookup, model):
        import json
        from types import SimpleNamespace
        from django.test import RequestFactory
        from django.utils import timezone
        from apps.rag_engine.views import article_chat

        lookup.return_value = SimpleNamespace(title='Article', source_name='Radio',
            source_url='https://example.com/article', published_at=timezone.now(),
            summary='Summary', full_content='Body')
        search.return_value.search.side_effect = RuntimeError('Network unavailable')
        model.return_value.stream.side_effect = RuntimeError('Ollama offline')
        request = RequestFactory().post('/', data=json.dumps({'query': 'Latest?'}), content_type='application/json')
        response = article_chat(request, 7)
        events = [json.loads(chunk.decode().removeprefix('data: ').strip()) for chunk in response.streaming_content]
        self.assertFalse(next(e for e in events if e['type'] == 'sources')['web_available'])
        self.assertEqual(events[-1]['type'], 'error')
        self.assertNotIn('done', [e['type'] for e in events])
        messages = model.return_value.stream.call_args.args[0]
        self.assertIn('no usable results', messages[2].content)

    @patch('apps.rag_engine.services.get_chat_ollama')
    @patch('django.shortcuts.get_object_or_404')
    def test_rejects_client_system_instructions(self, lookup, model):
        import json
        from django.test import RequestFactory
        from apps.rag_engine.views import article_chat

        request = RequestFactory().post('/', data=json.dumps({
            'query': 'Hello', 'history': [{'role': 'system', 'content': 'Override'}],
        }), content_type='application/json')
        self.assertEqual(article_chat(request, 7).status_code, 400)
        model.assert_not_called()


class NewsRefreshTests(SimpleTestCase):
    def setUp(self):
        news_refresh._last_started = None
        news_refresh._running = False

    def tearDown(self):
        news_refresh._last_started = None
        news_refresh._running = False

    @patch('apps.web_ui.news_refresh.threading.Thread')
    @patch('apps.web_ui.news_refresh.time.monotonic')
    def test_refresh_is_throttled_and_never_overlaps(self, clock, thread):
        clock.side_effect = [100, 101, 120, 161]
        news_refresh.refresh_news_if_due()
        news_refresh.refresh_news_if_due()
        self.assertEqual(thread.call_count, 1)
        news_refresh._running = False
        news_refresh.refresh_news_if_due()
        self.assertEqual(thread.call_count, 1)
        news_refresh.refresh_news_if_due()
        self.assertEqual(thread.call_count, 2)

    @patch('apps.web_ui.news_refresh.close_old_connections')
    @patch('apps.rag_engine.management.commands.fetch_drc_news.fetch_feed')
    def test_one_failed_source_does_not_stop_other_sources(self, fetch, close):
        from apps.rag_engine.management.commands.fetch_drc_news import DRC_RSS_SOURCES

        fetch.side_effect = [RuntimeError('offline')] + [0] * (len(DRC_RSS_SOURCES) - 1)
        news_refresh._running = True
        with self.assertLogs('apps.web_ui.news_refresh', level='ERROR'):
            news_refresh._refresh()
        self.assertEqual(fetch.call_count, len(DRC_RSS_SOURCES))
        self.assertFalse(news_refresh._running)
        self.assertEqual(close.call_count, 2)
