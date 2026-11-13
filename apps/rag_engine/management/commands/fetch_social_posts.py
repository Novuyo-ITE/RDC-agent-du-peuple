from django.core.management.base import BaseCommand, CommandError
from apps.web_ui.social_sources import import_social_posts, repair_imported_posts


class Command(BaseCommand):
    help = 'Discover public DRC social publications indexed by Tavily and import them into Community.'

    def add_arguments(self, parser):
        parser.add_argument('--repair-only', action='store_true', help='Clean stored imports without calling Tavily.')
        parser.add_argument('--images-only', action='store_true', help='Find original photos for existing X posts without Tavily searches.')
        parser.add_argument('--content-only', action='store_true', help='Recover full text and media for existing X posts without Tavily searches.')
        parser.add_argument('--force-images', action='store_true', help='Bypass cached failures when retrying missing photos.')
        parser.add_argument('--limit', type=int, default=30, help='Maximum older posts to check for photos.')
        parser.add_argument('--rounds', type=int, default=1, help='Discovery rounds across the rotating source catalogue (1-4).')

    def handle(self, *args, **options):
        try:
            if options['images_only'] or options['content_only']:
                from apps.web_ui.social_images import backfill_social_images
                self.stdout.write(f'Posts with photos recovered: {backfill_social_images(limit=max(1,min(options["limit"],200)),force=options["force_images"],include_text=options["content_only"])}')
                return
            repaired = repair_imported_posts()
            self.stdout.write(f"Stored imports: {repaired['cleaned']} cleaned; {repaired['hidden']} hidden")
            if options['repair_only']:
                return
            total = 0
            for _ in range(max(1,min(options['rounds'],4))):
                status = import_social_posts()
                total += status['created']
                self.stdout.write(f"Discovery round: {status['created']} new posts; state={status['state']}")
        except Exception as exc:
            raise CommandError('Social import failed. Check the server Tavily key, connection and database.') from exc
        self.stdout.write(self.style.SUCCESS(f"Social discovery: {total} new posts; state={status['state']}"))
