from io import BytesIO
from unittest.mock import patch
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.utils import timezone
from apps.rag_engine.models import OfficialNews, CommunityPost
from apps.rag_engine.news_policy import news_allowed


@override_settings(COMMUNITY_AUTO_BRIEFS=False,COMMUNITY_SOCIAL_DISCOVERY=False)
class NewsPolicyTests(TestCase):
    def article(self,title,**kwargs):
        return OfficialNews.objects.create(title=title,slug='test-'+str(OfficialNews.objects.count()),
            source_name='RFI Afrique',source_url='https://www.rfi.fr/fr/afrique/test',published_at=timezone.now(),**kwargs)

    def test_rfi_requires_drc_connection_and_does_not_confuse_the_two_congos(self):
        for title in ('RDC : la diplomatie régionale','Les services publics de Kinshasa','Accord sur la République démocratique du Congo'):
            self.assertTrue(news_allowed('RFI Afrique','https://rfi.fr/test',title))
        for title in ('Somalie : le prix du carburant','Congo-Brazzaville : les élections','Bénin : le Conseil économique'):
            self.assertFalse(news_allowed('RFI Afrique','https://rfi.fr/test',title))
        self.assertTrue(news_allowed('Radio Okapi','https://radiookapi.net/test','Une annonce locale'))
        self.assertFalse(news_allowed('Other label','https://www.rfi.fr/test','Somalie et pêche'))

    @patch('apps.web_ui.news_refresh.refresh_news_if_due')
    def test_unrelated_rfi_is_hidden_in_news_counts_community_ai_and_direct_links(self,refresh):
        foreign=self.article('Somalie : les pêcheurs face à la crise')
        local=self.article('RDC : réforme des services publics')
        brief=CommunityPost.objects.create(kind='ai',title=foreign.title,body='Ancien résumé',source_article=foreign)
        response=self.client.get('/actualites/')
        self.assertEqual(list(response.context['news_list']),[local])
        self.assertEqual(response.context['total_count'],1)
        self.assertIsNone(self.client.get(f'/actualites/?article={foreign.pk}').context['deep_link_article'])
        self.assertEqual(self.client.get(f'/api/community/news/{foreign.pk}/comments/').status_code,404)
        self.assertEqual(self.client.get(f'/api/community/post/{brief.pk}/comments/').status_code,404)
        self.assertFalse(self.client.get('/api/community/feed/?kind=ai').json()['items'])
        self.assertEqual([i['id'] for i in self.client.get('/api/community/feed/?kind=news').json()['items']],[local.pk])

    def test_relevance_in_article_text_is_supported(self):
        article=self.article('Un accord régional',full_content='Cet accord concerne la République démocratique du Congo.')
        self.assertTrue(OfficialNews.objects.approved().filter(pk=article.pk).exists())

    def test_cleanup_unapproves_without_deleting_or_reapproving_hidden_articles(self):
        outside=self.article('Tanzanie : élections')
        local=self.article('Kinshasa : une rencontre')
        hidden=self.article('RDC : ancien article',is_verified=False)
        call_command('enforce_news_policy',stdout=__import__('io').StringIO())
        outside.refresh_from_db();local.refresh_from_db();hidden.refresh_from_db()
        self.assertFalse(outside.is_verified);self.assertTrue(local.is_verified);self.assertFalse(hidden.is_verified)
        self.assertEqual(OfficialNews.objects.count(),3)

    def test_rss_import_skips_unrelated_rfi(self):
        from apps.rag_engine.management.commands.fetch_drc_news import DRC_RSS_SOURCES,fetch_feed
        source=next(s for s in DRC_RSS_SOURCES if s['name']=='RFI Afrique')
        xml=b'<rss version="2.0"><channel><item><title>Somalie: le prix du carburant</title><link>https://rfi.fr/somalia</link><description>Les pecheurs de Somalie sont concernes.</description></item><item><title>RDC: un accord pour Kinshasa</title><link>https://rfi.fr/rdc</link><description>Une rencontre a Kinshasa.</description></item></channel></rss>'
        with patch('urllib.request.urlopen') as request,patch('apps.rag_engine.management.commands.fetch_drc_news.fetch_article_body',return_value=''),patch('apps.rag_engine.management.commands.fetch_drc_news._scrape_article_image',return_value=''):
            request.return_value.__enter__.return_value=BytesIO(xml)
            self.assertEqual(fetch_feed(source),1)
        self.assertEqual(OfficialNews.objects.get().source_url,'https://rfi.fr/rdc')
