from datetime import timedelta

from bs4 import BeautifulSoup
from django.test import TestCase
from django.utils import timezone

from apps.rag_engine.models import OfficialNews

from .service_news import recent_service_news


class ServiceNewsTests(TestCase):
    def article(self, slug, title, when, **kwargs):
        return OfficialNews.objects.create(
            slug=slug, title=title, source_name=kwargs.pop('source_name', 'Radio Okapi'),
            source_url=kwargs.pop('source_url', f'https://example.org/{slug}'),
            summary=kwargs.pop('summary', ''), full_content='', published_at=when, **kwargs)

    def test_filters_news_and_orders_recent_first(self):
        now = timezone.now()
        oldest = self.article('old', 'Nouveau passeport', now - timedelta(days=2))
        newest = self.article('new', 'Un guichet unique ouvre à Kinshasa', now - timedelta(hours=1))
        self.article('unrelated', 'Un match de football à Goma', now)
        self.article('future', 'Nouveau passeport', now + timedelta(days=1))
        self.article('hidden', 'Nouveau passeport', now, is_verified=False)
        self.article('rfi-foreign', 'Nouveau passeport au Sénégal', now,
                     source_name='RFI Afrique', source_url='https://www.rfi.fr/fr/afrique/senegal')
        self.assertEqual(list(recent_service_news()), [newest, oldest])

    def test_carousel_renders_article_photo_source_and_exact_news_link(self):
        now = timezone.now()
        older = self.article('passport', 'Nouveau passeport', now - timedelta(days=1),
                             image_url='https://example.org/passport.jpg')
        newer = self.article('tax', 'Nouvelle taxe', now, image_url='https://example.org/tax.jpg',
                             summary='Résumé à ne pas afficher dans le carrousel.')
        response = self.client.get('/demarches/')
        self.assertEqual(response.status_code, 200)
        page = BeautifulSoup(response.content, 'html.parser')
        slides = page.select('[data-service-slide]')
        self.assertEqual(len(slides), 2)
        for index, (slide, article) in enumerate(zip(slides, [newer, older])):
            self.assertEqual(slide.has_attr('hidden'), bool(index))
            self.assertEqual(slide.select_one('.svc-news-photo img')['src'], article.image_url)
            self.assertEqual(slide.select_one('h2 a')['href'], f'/actualites/?article={article.pk}')
            self.assertEqual(slide.select_one('[data-source-favicon]')['data-source-favicon'], article.source_url)
            self.assertIn(article.source_name, slide.get_text())
        self.assertIsNotNone(page.select_one('[data-service-carousel-action="toggle"]'))
        self.assertEqual(len(page.select('.svc-news-slide .svc-news-meta .svc-news-controls')), 2)
        self.assertIsNone(page.select_one('.svc-news-stage > .svc-news-controls'))
        self.assertIsNone(page.select_one('[data-service-carousel-position]'))
        for button in page.select('.svc-news-controls button'):
            self.assertTrue(button.get('aria-label'))
            self.assertIsNotNone(button.select_one('svg'))
            self.assertEqual(button.get_text(strip=True), '')
        self.assertNotIn(newer.summary, page.select_one('[data-service-carousel]').get_text())
        self.assertEqual(len(page.select('.svc-path-row')), 3)

    def test_empty_carousel_displays_a_clear_message_without_controls(self):
        response = self.client.get('/demarches/')
        page = BeautifulSoup(response.content, 'html.parser')
        self.assertIn('Aucune actualité', page.select_one('.svc-news-empty').get_text())
        self.assertIsNone(page.select_one('[data-service-carousel-action]'))
