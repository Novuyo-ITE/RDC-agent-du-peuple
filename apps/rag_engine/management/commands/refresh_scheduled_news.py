"""One finite news import for Railway cron, independent of web requests."""
import logging
from django.core.management.base import BaseCommand, CommandError
from django.db import close_old_connections, connections
from .fetch_drc_news import DRC_RSS_SOURCES, fetch_feed

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Import latest RSS news for a scheduled background job."

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
            if failures == len(DRC_RSS_SOURCES):
                raise CommandError('All news sources failed; inspect job logs')
        finally:
            connections.close_all()
