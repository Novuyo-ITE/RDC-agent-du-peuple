from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase, override_settings

from apps.rag_engine.models import CommunityPost
from apps.rag_engine.web_search import TavilyDRCSearchTool, TavilySearchError
from apps.web_ui.social_sources import canonical_post_url, import_social_posts, refresh_social_if_due, discovery_status


@override_settings(TAVILY_API_KEY='test-key', COMMUNITY_SOCIAL_DISCOVERY=True, COMMUNITY_AUTO_BRIEFS=False)
class SocialDiscoveryTests(TestCase):
    def setUp(self):
        cache.clear()
        photo_fetch = patch('apps.web_ui.social_images.fetch_x_photos', return_value=[])
        photo_fetch.start()
        self.addCleanup(photo_fetch.stop)

    def record(self, url='https://twitter.com/radiookapi/status/123?utm_source=share', title='RDC : transports à Kinshasa'):
        return {'url': url, 'title': title, 'snippet': 'Une publication publique sur les transports à Kinshasa en RDC.'}

    @patch('apps.rag_engine.web_search.TavilyDRCSearchTool.results')
    def test_imports_sources_and_deduplicates_twitter_aliases(self, search):
        search.side_effect = [[self.record()], [self.record('https://x.com/radiookapi/status/123')], [], [], [], []]
        result = import_social_posts()
        self.assertEqual(result['created'], 1)
        post = CommunityPost.objects.get()
        self.assertEqual(post.kind, 'social')
        self.assertEqual(post.source_url, 'https://x.com/i/web/status/123')
        self.assertEqual(post.platform, 'X / Twitter')
        self.assertIsNotNone(post.import_key)
        self.assertEqual(post.body, self.record()['snippet'])
        self.assertEqual(search.call_args_list[0].kwargs['time_range'], 'week')
        search.side_effect = [[self.record()], [], [], [], [], []]
        post.is_visible=False;post.save()
        self.assertEqual(import_social_posts()['created'], 0)
        self.assertFalse(CommunityPost.objects.get().is_visible)

    def test_only_accepts_social_post_links(self):
        for url in ['https://x.com/example', 'https://x.com/search?q=RDC', 'https://evil.x.com/example/status/1',
                    'https://example.org/news', 'javascript:alert(1)', 'https://facebook.com/login',
                    'https://youtube.com/@profile', 'https://instagram.com/person',
                    'https://user:password@x.com/example/status/1', 'https://facebook.com/agency/posts/123',
                    'https://www.tiktok.com/@agency/video/123']:
            self.assertIsNone(canonical_post_url(url), url)
        for url in ['https://instagram.com/p/Abcd/',
                    'https://www.youtube.com/watch?v=Abcdef123&feature=share',
                    'https://www.linkedin.com/posts/agency_123',
                    'https://bsky.app/profile/agency/post/abc', 'https://www.threads.net/@agency/post/abc']:
            self.assertIsNotNone(canonical_post_url(url), url)
        self.assertEqual(canonical_post_url('https://youtu.be/Abcdef123?si=tracking'),
                         canonical_post_url('https://youtube.com/watch?v=Abcdef123'))

    @patch('apps.rag_engine.web_search.TavilyDRCSearchTool.results')
    def test_rejects_unrelated_and_incomplete_hits(self, search):
        search.return_value = [self.record('https://example.org/story'),
            {'url':'https://x.com/example/status/1','title':'Congo Brazzaville','snippet':'Actualités de Brazzaville'},
            {'url':'https://x.com/example/status/2','title':'RDC','snippet':''}]
        result=import_social_posts()
        self.assertEqual(result['created'],0)
        self.assertEqual(result['state'],'ready')

    @patch('apps.rag_engine.web_search.TavilyDRCSearchTool.results')
    def test_partial_failure_keeps_successful_imports(self, search):
        search.side_effect = [TavilySearchError('offline'), [self.record('https://x.com/radiookapi/status/123')], [], [], [], []]
        result=import_social_posts()
        self.assertEqual(result['state'],'partial')
        self.assertEqual(result['created'],1)

    @patch('apps.rag_engine.web_search.TavilyDRCSearchTool.results', side_effect=TavilySearchError('offline'))
    def test_total_failure_preserves_existing_posts_and_reports_error(self, search):
        CommunityPost.objects.create(title='Existing',body='Keep me')
        with self.assertRaises(TavilySearchError):
            import_social_posts()
        self.assertEqual(CommunityPost.objects.count(),1)
        self.assertEqual(discovery_status()['state'],'error')

    @override_settings(TAVILY_API_KEY='')
    @patch('apps.web_ui.social_sources.threading.Thread')
    def test_missing_key_never_starts_background_search(self, thread):
        refresh_social_if_due()
        thread.assert_not_called()
        self.assertEqual(discovery_status()['state'],'unconfigured')

    @patch('apps.web_ui.social_sources.threading.Thread')
    def test_background_refresh_is_throttled(self, thread):
        refresh_social_if_due();refresh_social_if_due()
        self.assertEqual(thread.call_count,1)
        self.assertEqual(discovery_status()['state'],'refreshing')

    @patch('apps.rag_engine.web_search.TavilyDRCSearchTool._post',return_value={'results':[]})
    def test_tavily_payload_includes_domain_and_recency_filters(self, post):
        TavilyDRCSearchTool().results('RDC',include_domains=['x.com'],time_range='week')
        self.assertEqual(post.call_args.args[1]['include_domains'],['x.com'])
        self.assertEqual(post.call_args.args[1]['time_range'],'week')

    @patch('apps.web_ui.social_sources.refresh_social_if_due')
    def test_feed_identifies_discovery_without_forging_publication_date(self, refresh):
        CommunityPost.objects.create(kind='social',title='RDC sur X',body='Extrait indexé',
            source_url='https://x.com/i/web/status/123',platform='X / Twitter',import_key='abc')
        item=self.client.get('/api/community/feed/?kind=social').json()['items'][0]
        self.assertEqual(item['discovered_by'],'Tavily')
