from django.core.management.base import BaseCommand
from django.db.models import Q
from apps.rag_engine.models import OfficialNews
from apps.rag_engine.management.commands.fetch_drc_news import _scrape_article_image


class Command(BaseCommand):
    help = 'Recover original source images for stored approved news missing a picture.'

    def add_arguments(self, parser):
        parser.add_argument('--limit', type=int, default=20)

    def handle(self, *args, **options):
        articles=OfficialNews.objects.approved().filter(Q(image_url='')|Q(image_url__isnull=True)).order_by('-published_at')[:max(1,min(options['limit'],100))]
        added=0
        for article in articles:
            image=_scrape_article_image(article.source_url)
            if image:
                OfficialNews.objects.filter(pk=article.pk).update(image_url=image)
                added+=1
        self.stdout.write(f'News source pictures recovered: {added}')
