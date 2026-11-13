from django.core.management.base import BaseCommand, CommandError
from apps.rag_engine.models import OfficialNews
from apps.web_ui.community import generate_brief


class Command(BaseCommand):
    help = 'Generate short, source-linked AI community posts from stored news (requires Ollama).'

    def add_arguments(self, parser):
        parser.add_argument('--limit', type=int, default=3)

    def handle(self, *args, **options):
        limit = max(1, min(options['limit'], 20))
        from apps.rag_engine.models import CommunityPost
        completed = CommunityPost.objects.filter(source_article__isnull=False, source_metadata__news_summary_version=1).values('source_article_id')
        articles = OfficialNews.objects.approved().exclude(pk__in=completed).order_by('-published_at')[:limit]
        for article in articles:
            try:
                post, created = generate_brief(article)
            except Exception as exc:
                raise CommandError('Could not generate a brief. Check Ollama and database storage.') from exc
            self.stdout.write(f'{"Created" if created else "Existing"}: {post.pk} — {post.title}')
