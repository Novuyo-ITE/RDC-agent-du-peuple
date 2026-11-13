from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone

from apps.rag_engine.models import OfficialNews


@patch('apps.web_ui.news_refresh.refresh_news_if_due')
class NewsSourceTests(TestCase):
    def setUp(self):
        self.local = OfficialNews.objects.create(
            title='Local reporting', slug='local-reporting', source_name='Radio Okapi',
            source_url='https://www.radiookapi.net/local', category='securite',
            published_at=timezone.now() - timedelta(days=1))
        self.rfi = OfficialNews.objects.create(
            title='RDC : international reporting', slug='international-reporting', source_name='RFI Afrique',
            source_url='https://www.rfi.fr/fr/afrique/story', category='international',
            published_at=timezone.now())

    def test_all_uses_the_latest_approved_story_regardless_of_source(self, refresh):
        response = self.client.get('/actualites/')
        self.assertEqual(list(response.context['news_list']), [self.rfi, self.local])

    def test_all_journal_lead_changes_when_a_new_story_arrives(self, refresh):
        from bs4 import BeautifulSoup
        first=self.client.get('/actualites/?category=all&period=all')
        self.assertEqual(first.context['news_list'][0],self.rfi)
        article=OfficialNews.objects.create(title='Kinshasa : nouvelle publication',slug='latest-lead',
            source_name='Autre média',source_url='https://example.org/kinshasa',
            published_at=timezone.now()+timedelta(minutes=1))
        second=self.client.get('/actualites/?category=all&period=all')
        self.assertEqual(second.context['news_list'][0],article)
        markup=BeautifulSoup(second.content,'html.parser')
        self.assertEqual(markup.select_one('.edition-lead h2').get_text(strip=True),article.title)
        self.assertIsNotNone(markup.select_one('#news-update-button'))
        self.assertEqual(second['Cache-Control'],'no-store')

    def test_featured_stories_use_latest_articles_and_their_own_links(self, refresh):
        from bs4 import BeautifulSoup
        for index in range(5):
            OfficialNews.objects.create(
                title=f'Actualité {index}', slug=f'featured-{index}',
                source_name=f'Source {index}', source_url=f'https://example.org/{index}',
                published_at=timezone.now() + timedelta(minutes=index + 1))

        response = self.client.get('/actualites/?category=all')
        slides = BeautifulSoup(response.content, 'html.parser').select('.edition-lead-slide')
        expected = list(response.context['news_list'][:5])
        self.assertEqual([int(slide['data-featured-id']) for slide in slides],
                         [article.pk for article in expected])
        for index, (slide, article) in enumerate(zip(slides, expected)):
            self.assertEqual(slide.select_one('h2').get_text(strip=True), article.title)
            self.assertIn(str(article.pk), slide.select_one('h2 button')['onclick'])
            self.assertIn(article.source_name, slide.get_text())
            self.assertEqual(slide.has_attr('hidden'), index != 0)

    def test_rfi_only_appears_in_international_category(self, refresh):
        response = self.client.get('/actualites/?category=international')
        self.assertEqual(list(response.context['news_list']), [self.rfi])
        response = self.client.get('/actualites/?category=securite')
        self.assertEqual(list(response.context['news_list']), [self.local])

    def test_news_grid_has_nine_latest_cards_and_paginates_without_skipping_stories(self,refresh):
        from bs4 import BeautifulSoup
        for index in range(20):
            OfficialNews.objects.create(title=f'Kinshasa : nouvelle {index}',slug=f'grid-{index}',
                source_name='Radio Okapi',source_url=f'https://radiookapi.net/{index}',
                published_at=timezone.now()+timedelta(minutes=index))
        first=self.client.get('/actualites/?category=all')
        second=self.client.get('/actualites/?category=all&page=2')
        cards=BeautifulSoup(first.content,'html.parser').select('.edition-news-grid .edition-news-card')
        next_cards=BeautifulSoup(second.content,'html.parser').select('.edition-news-grid .edition-news-card')
        self.assertEqual(len(cards),9)
        self.assertEqual(len(next_cards),9)
        ids=[int(card['data-article-id']) for card in cards]
        next_ids=[int(card['data-article-id']) for card in next_cards]
        expected=list(OfficialNews.objects.approved().order_by('-published_at','-pk').values_list('pk',flat=True))
        self.assertEqual(ids,expected[:9])
        self.assertEqual(next_ids,expected[9:18])
        self.assertFalse(set(ids)&set(next_ids))

    def test_rfi_import_overrides_topic_keywords(self, refresh):
        from io import BytesIO
        from apps.rag_engine.management.commands.fetch_drc_news import DRC_RSS_SOURCES, fetch_feed
        source = next(source for source in DRC_RSS_SOURCES if source['name'] == 'RFI Afrique')
        feed = b'<rss version="2.0"><channel><title>RFI</title><item><title>Goma: offensive militaire au Nord-Kivu</title><link>https://www.rfi.fr/test-import</link><description>FARDC et gouvernement</description></item></channel></rss>'
        with patch('urllib.request.urlopen') as request, \
                patch('apps.rag_engine.management.commands.fetch_drc_news.fetch_article_body', return_value=''), \
                patch('apps.rag_engine.management.commands.fetch_drc_news._scrape_article_image', return_value=''):
            request.return_value.__enter__.return_value = BytesIO(feed)
            self.assertEqual(fetch_feed(source), 1)
        self.assertEqual(OfficialNews.objects.get(source_url='https://www.rfi.fr/test-import').category,
                         'international')


class SentinelleSourceTests(TestCase):
    def test_two_public_feeds_are_enabled(self):
        from apps.rag_engine.management.commands.fetch_drc_news import DRC_RSS_SOURCES
        feeds = {source['url'] for source in DRC_RSS_SOURCES if source.get('enabled', True)}
        self.assertIn('https://lasentinelle.cd/feed/', feeds)
        self.assertIn('https://sentineldrc.org/feed/', feeds)

    @patch('urllib.request.urlopen')
    def test_authenticated_source_is_registered_without_attempting_rss_fetch(self, request):
        from apps.rag_engine.management.commands.fetch_drc_news import DRC_RSS_SOURCES, fetch_feed
        source = next(source for source in DRC_RSS_SOURCES
                      if source['url'] == 'https://www.sentinelle-rdc.com/')
        self.assertEqual(fetch_feed(source), 0)
        request.assert_not_called()
