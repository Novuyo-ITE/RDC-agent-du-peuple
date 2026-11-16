"""One finite RSS and social import for Railway cron, independent of web requests."""
import logging
import time
from django.conf import settings
from apps.web_ui.social_sources import import_social_posts
from django.core.management.base import BaseCommand, CommandError
from django.db import close_old_connections, connections
from .fetch_drc_news import DRC_RSS_SOURCES, fetch_feed

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Import RSS news and indexed social posts for a scheduled background job."

    def add_arguments(self, parser):
        parser.add_argument('--max-per-source', type=int, default=15)

    def handle(self, *args, **options):
        limit = options['max_per_source']
        if limit < 1:
            raise CommandError('--max-per-source must be positive')
        saved = failures = 0
        close_old_connections()
        try:
            for source in DRC_RSS_SOURCES:
                try:
                    count = fetch_feed(source, max_items=limit, stdout=self.stdout)
                    saved += count
                    self.stdout.write(f"{source['name']}: {count} new articles")
                except Exception:
                    failures += 1
                    logger.exception('Scheduled news import failed for %s', source['name'])
                finally:
                    close_old_connections()
            self.stdout.write(f'Completed: {saved} new articles; {failures} failed sources')
            # Run synchronously: cron must not exit while a daemon thread imports X posts.
            if not getattr(settings, 'TAVILY_API_KEY', ''):
                self.stderr.write('X/social refresh skipped: configure TAVILY_API_KEY on news-refresh.')
            elif not getattr(settings, 'COMMUNITY_SOCIAL_DISCOVERY', True):
                self.stderr.write('X/social refresh skipped: COMMUNITY_SOCIAL_DISCOVERY is disabled.')
            else:
                try:
                    # LocMemCache resets for every cron process; use the schedule slot
                    # to rotate accounts across executions without a persistent cache.
                    result = import_social_posts(offset=int(time.time() // 900))
                    self.stdout.write(f"X/social: {result['created']} new posts; state={result['state']}")
                    if result['state'] == 'partial':
                        self.stderr.write('Some social searches failed; existing posts are preserved.')
                except Exception:
                    logger.exception('Scheduled X/social import failed; RSS results are preserved')
                    self.stderr.write('X/social refresh failed; inspect logs. RSS results are preserved.')
                finally:
                    close_old_connections()
            if failures == len(DRC_RSS_SOURCES):
                raise CommandError('All news sources failed; inspect job logs')
        finally:
            connections.close_all()
