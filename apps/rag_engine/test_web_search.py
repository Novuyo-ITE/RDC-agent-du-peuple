from unittest.mock import Mock, patch

import requests
from django.test import SimpleTestCase, override_settings

from .web_search import TavilyDRCSearchTool, TavilySearchError, article_image


@override_settings(TAVILY_API_KEY='test-server-secret', TAVILY_SEARCH_DEPTH='basic')
class TavilyTests(SimpleTestCase):
    @patch('apps.rag_engine.web_search.requests.post')
    def test_latest_news_uses_recent_search_and_keeps_publication_date(self, post):
        post.return_value = Mock(ok=True)
        post.return_value.json.return_value = {'results': [{
            'title': 'Une actualité', 'url': 'https://example.cd/article', 'content': 'Texte',
            'published_date': '2026-11-04', 'raw_content': '![Photo](https://example.cd/photo.jpg)'}]}
        result = TavilyDRCSearchTool().search('dernières actualités minières')
        self.assertEqual(post.call_args.kwargs['json']['time_range'], 'month')
        source = result['structured'][0]
        self.assertEqual(source['published_at'], '2026-11-04')
        self.assertEqual(source['image_url'], 'https://example.cd/photo.jpg')
        self.assertNotEqual(source['published_at'], source['retrieved_at'])

    def test_article_photo_comes_from_same_result_body(self):
        body = '![Logo](/logo.png)\nActualité\n![Mine](/photos/mine.jpg)'
        self.assertEqual(article_image(body, 'https://example.cd/news/mines'), 'https://example.cd/photos/mine.jpg')
        self.assertEqual(article_image('No picture', 'https://example.cd/news'), '')
        self.assertEqual(article_image('![Bad](javascript:alert)', 'https://example.cd/news'), '')

    @patch('apps.rag_engine.web_search.requests.post')
    def test_search_authentication_and_existing_chat_contract(self, post):
        post.return_value = Mock(ok=True)
        post.return_value.json.return_value = {'results': [
            {'title': 'Official procedure', 'url': 'https://diplomatie.gouv.cd/services',
             'content': 'Published instructions', 'raw_content': 'Full page', 'favicon': 'https://example.com/favicon.ico'},
            {'title': 'Unsafe URL', 'url': 'javascript:alert(1)'},
        ]}
        result = TavilyDRCSearchTool(max_results=2).search('Passport')
        self.assertEqual(result['status'], 'success')
        self.assertEqual(result['source'], 'Tavily')
        self.assertEqual(len(result['structured']), 1)
        self.assertIn('Published instructions', result['results_raw'])
        self.assertNotIn('test-server-secret', str(result))
        args, kwargs = post.call_args
        self.assertEqual(args[0], 'https://api.tavily.com/search')
        self.assertEqual(kwargs['headers']['Authorization'], 'Bearer test-server-secret')
        self.assertNotIn('api_key', kwargs['json'])
        self.assertEqual(kwargs['json']['max_results'], 2)
        self.assertEqual(kwargs['json']['query'], 'Passport RDC')
        self.assertEqual(result['structured'][0]['raw_content'], 'Full page')
        self.assertEqual(kwargs['json']['include_raw_content'], 'markdown')

    @patch('apps.rag_engine.web_search.requests.post')
    def test_search_discovery_interface_retains_full_source_and_domain_filter(self, post):
        post.return_value = Mock(ok=True)
        post.return_value.json.return_value = {'results': [
            {'url': 'https://arsp.cd/faq', 'raw_content': 'Full official content'}]}
        tool = TavilyDRCSearchTool()
        records = tool.wrapper.results('registration', max_results=5, include_domains=['arsp.cd'])
        self.assertEqual(records[0]['link'], 'https://arsp.cd/faq')
        self.assertEqual(records[0]['raw_content'], 'Full official content')
        self.assertEqual(post.call_args.kwargs['json']['include_domains'], ['arsp.cd'])

    @patch('apps.rag_engine.web_search.requests.post')
    def test_extraction_uses_tavily_full_content_endpoint(self, post):
        post.return_value = Mock(ok=True)
        post.return_value.json.return_value = {'results': [{'raw_content': 'Entire source body'}]}
        result = TavilyDRCSearchTool().extract(['https://conadep.cd/procedure-obtention/'])
        self.assertEqual(result['results'][0]['raw_content'], 'Entire source body')
        self.assertEqual(post.call_args.args[0], 'https://api.tavily.com/extract')
        self.assertEqual(post.call_args.kwargs['json']['extract_depth'], 'advanced')

    @patch('apps.rag_engine.web_search.requests.post')
    def test_failures_never_echo_provider_body_or_request_credentials(self, post):
        post.return_value = Mock(ok=False, status_code=401, text='test-server-secret')
        with self.assertLogs('apps.rag_engine.web_search', level='WARNING') as captured:
            result = TavilyDRCSearchTool().search('test')
        self.assertEqual(result['status'], 'error')
        self.assertNotIn('test-server-secret', str(result) + str(captured.output))
        post.side_effect = requests.ConnectionError('test-server-secret')
        with self.assertRaises(TavilySearchError) as caught:
            TavilyDRCSearchTool().results('test')
        self.assertNotIn('test-server-secret', str(caught.exception))

    @override_settings(TAVILY_API_KEY='')
    @patch('apps.rag_engine.web_search.requests.post')
    def test_missing_key_is_explicit_and_does_not_make_network_request(self, post):
        tool = TavilyDRCSearchTool()
        self.assertIsNone(tool.wrapper)
        with self.assertLogs('apps.rag_engine.web_search', level='WARNING'):
            self.assertEqual(tool.search('test')['status'], 'error')
        post.assert_not_called()
