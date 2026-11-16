from unittest.mock import patch
from django.test import TestCase, RequestFactory, override_settings
from django.utils import timezone
from apps.rag_engine.models import OfficialNews
from apps.web_ui.views import landing_view


@patch('apps.web_ui.news_refresh.refresh_news_if_due')
class LandingNewsLoadingTests(TestCase):
    def article(self, slug, image):
        return OfficialNews.objects.create(title='Kinshasa: services publics', slug=slug,
            source_name='Radio Okapi', source_url='https://www.radiookapi.net/'+slug,
            image_url=image, summary='Resume', full_content='Long article '*1000,
            published_at=timezone.now())

    @patch('apps.web_ui.views.render')
    def test_cards_include_null_images_without_loading_article_bodies(self, render, refresh):
        photographed = self.article('photo', 'https://www.radiookapi.net/photo.jpg')
        no_image = self.article('no-image', None)
        blank_image = self.article('blank', '')
        landing_view(RequestFactory().get('/'))
        context = render.call_args.args[2]
        self.assertEqual([item.pk for item in context['latest_news']],
                         [photographed.pk, blank_image.pk, no_image.pk])
        for item in context['latest_news']:
            self.assertIn('full_content', item.get_deferred_fields())
        with self.assertNumQueries(0):
            for item in context['latest_news']:
                _ = item.title, item.image_url, item.summary, item.source_name

    def test_landing_renders_content_without_waiting_for_external_images(self, refresh):
        self.article('photo', 'https://www.radiookapi.net/photo.jpg')
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Kinshasa: services publics')
        self.assertContains(response, 'js/landing-news.js')
        refresh.assert_not_called()
        self.assertContains(response, 'img/news-placeholder.svg')


@override_settings(TAVILY_API_KEY='')
class ScheduledNewsTests(TestCase):
    @patch('apps.rag_engine.management.commands.refresh_scheduled_news.fetch_feed')
    def test_scheduled_command_runs_without_visitors_and_preserves_other_sources(self, fetch):
        from io import StringIO
        from django.core.management import call_command
        from apps.rag_engine.management.commands.refresh_scheduled_news import DRC_RSS_SOURCES
        fetch.side_effect = [RuntimeError('offline')] + [1] * (len(DRC_RSS_SOURCES) - 1)
        with self.assertLogs('apps.rag_engine.management.commands.refresh_scheduled_news', level='ERROR'):
            call_command('refresh_scheduled_news', max_per_source=3, stdout=StringIO())
        self.assertEqual(fetch.call_count, len(DRC_RSS_SOURCES))
        self.assertTrue(all(call.kwargs['max_items'] == 3 for call in fetch.call_args_list))

    @patch('apps.rag_engine.management.commands.refresh_scheduled_news.fetch_feed')
    def test_invalid_limit_does_not_contact_sources(self, fetch):
        from django.core.management import call_command, CommandError
        with self.assertRaises(CommandError):
            call_command('refresh_scheduled_news', max_per_source=0)
        fetch.assert_not_called()


@override_settings(TAVILY_API_KEY='test-key', COMMUNITY_SOCIAL_DISCOVERY=True)
class ScheduledSocialTests(TestCase):
    @patch('apps.rag_engine.management.commands.refresh_scheduled_news.import_social_posts')
    @patch('apps.rag_engine.management.commands.refresh_scheduled_news.fetch_feed', return_value=0)
    def test_same_job_runs_social_import_synchronously(self, feed, social):
        from io import StringIO
        from django.core.management import call_command
        social.return_value = {'created': 2, 'state': 'ready'}
        output = StringIO()
        call_command('refresh_scheduled_news', stdout=output)
        social.assert_called_once()
        self.assertIsInstance(social.call_args.kwargs['offset'], int)
        self.assertIn('X/social: 2 new posts', output.getvalue())

    @patch('apps.rag_engine.management.commands.refresh_scheduled_news.import_social_posts')
    @patch('apps.rag_engine.management.commands.refresh_scheduled_news.fetch_feed', side_effect=RuntimeError('offline'))
    def test_all_rss_failures_still_allow_social_import(self, feed, social):
        from io import StringIO
        from django.core.management import call_command, CommandError
        social.return_value = {'created': 1, 'state': 'ready'}
        with self.assertLogs('apps.rag_engine.management.commands.refresh_scheduled_news', level='ERROR'):
            with self.assertRaises(CommandError):
                call_command('refresh_scheduled_news', stdout=StringIO())
        social.assert_called_once()

    @patch('apps.rag_engine.management.commands.refresh_scheduled_news.import_social_posts', side_effect=RuntimeError('offline'))
    @patch('apps.rag_engine.management.commands.refresh_scheduled_news.fetch_feed', return_value=1)
    def test_social_failure_does_not_fail_successful_rss_import(self, feed, social):
        from io import StringIO
        from django.core.management import call_command
        with self.assertLogs('apps.rag_engine.management.commands.refresh_scheduled_news', level='ERROR'):
            call_command('refresh_scheduled_news', stdout=StringIO(), stderr=StringIO())
        self.assertGreater(feed.call_count, 0)
