from unittest.mock import patch
from django.test import TestCase, SimpleTestCase, override_settings

from .models import CommunityPost
from .social_research import news_request, search_live_x, stored_x_sources
from .services import DRCRagService


class SocialQueryTests(SimpleTestCase):
    def test_news_and_explicit_twitter_questions_are_recognised(self):
        self.assertTrue(news_request('Les dernières actualités en RDC'))
        self.assertTrue(news_request('Que dit Twitter sur les mines ?'))
        self.assertFalse(news_request('Comment renouveler mon passeport ?'))

    @override_settings(TAVILY_API_KEY='test')
    @patch('apps.rag_engine.social_research.fetch_x_photos')
    @patch('apps.rag_engine.social_research.TavilyDRCSearchTool')
    def test_live_search_only_keeps_selected_accounts_and_their_own_photos(self, searcher, fetch_photos):
        text = 'Les autorités congolaises annoncent une nouvelle réunion publique à Kinshasa.'
        searcher.return_value.results.return_value = [
            {'url':'https://x.com/radiookapi/status/123', 'title':'Actualité RDC', 'snippet':text, 'published_at':''},
            {'url':'https://x.com/unknown/status/456', 'title':'Autre', 'snippet':text},
            {'url':'https://facebook.com/radiookapi/posts/7', 'title':'Autre réseau', 'snippet':text},
        ]
        fetch_photos.return_value = ['https://pbs.twimg.com/media/actual-photo.jpg', 'https://example.com/other.jpg']
        sources = search_live_x('actualité Kinshasa')
        self.assertEqual(len(sources),1)
        self.assertEqual(sources[0]['url'],'https://x.com/i/web/status/123')
        self.assertEqual(sources[0]['image_url'],'https://pbs.twimg.com/media/actual-photo.jpg')
        self.assertEqual(sources[0]['published_at'],'')
        self.assertIn('non vérifié', sources[0]['excerpt_label'])
        fetch_photos.assert_called_once_with('https://x.com/i/web/status/123','radiookapi')
        self.assertEqual(searcher.return_value.results.call_args.kwargs['include_domains'],['x.com','twitter.com'])

    @override_settings(TAVILY_API_KEY='test')
    @patch('apps.rag_engine.social_research.fetch_x_photos', return_value=[])
    @patch('apps.rag_engine.social_research.TavilyDRCSearchTool')
    def test_post_without_own_photo_has_no_substitute_image(self, searcher, photos):
        searcher.return_value.results.return_value = [{'url':'https://x.com/radiookapi/status/123',
            'title':'Actualité RDC','snippet':'Une publication détaillée sur la réunion annoncée à Kinshasa.'}]
        self.assertEqual(search_live_x('Kinshasa')[0]['image_url'],'')


@override_settings(TAVILY_API_KEY='')
class StoredSocialTests(TestCase):
    def test_only_visible_selected_imports_are_used_and_discovery_is_not_publication_date(self):
        CommunityPost.objects.create(kind='social',platform='X / Twitter',title='Réunion à Kinshasa',
            body='Une réunion importante est annoncée à Kinshasa.',author='Radio',import_key='selected-post',
            source_url='https://x.com/i/web/status/123',source_metadata={'account':'radiookapi',
                'original_url':'https://x.com/radiookapi/status/123','images':['https://pbs.twimg.com/media/own.jpg'],
                'image_source':'x_embed'})
        CommunityPost.objects.create(kind='social',platform='X / Twitter',title='Réunion cachée',
            body='Une réunion cachée à Kinshasa.',author='Radio',import_key='hidden-post',is_visible=False,
            source_url='https://x.com/i/web/status/456',source_metadata={'account':'radiookapi',
                'original_url':'https://x.com/radiookapi/status/456'})
        result = stored_x_sources(['kinshasa'])
        self.assertEqual(len(result),1)
        self.assertEqual(result[0]['image_url'],'https://pbs.twimg.com/media/own.jpg')
        self.assertEqual(result[0]['published_at'],'')
        self.assertTrue(result[0]['retrieved_at'])

    @patch('apps.rag_engine.social_research.stored_x_sources', return_value=[])
    @patch('apps.rag_engine.social_research.search_live_x')
    @patch('apps.rag_engine.services.TavilyDRCSearchTool.search')
    @patch('apps.rag_engine.official_portals.find_matching_official_portals', return_value=[])
    def test_news_retrieval_includes_x_context_and_link_for_model(self, portals, web, social, stored):
        web.return_value = {'status':'success','structured':[]}
        social.return_value = [{'title':'Annonce à Kinshasa','institution':'Radio Okapi',
            'url':'https://x.com/i/web/status/123','image_url':'https://pbs.twimg.com/media/a.jpg',
            'text':'Une réunion a été annoncée.', 'source_kind':'social','published_at':'',
            'retrieved_at':'2026-11-07T10:00:00Z'}]
        result = DRCRagService.__new__(DRCRagService).retrieve_context('Les dernières actualités à Kinshasa')
        self.assertTrue(any(source['url'] == social.return_value[0]['url'] for source in result['sources']))
        self.assertIn('PUBLICATION X NON VÉRIFIÉE',result['context_text'])
        self.assertIn('Date de publication : inconnue',result['context_text'])
        social.assert_called_once()
