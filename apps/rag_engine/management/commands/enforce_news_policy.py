from django.core.management.base import BaseCommand
from apps.rag_engine.models import OfficialNews
from apps.rag_engine.news_policy import rfi_condition, drc_condition


class Command(BaseCommand):
    help = 'Unapprove stored RFI articles unrelated to the DRC, retaining their data and discussions.'

    def handle(self, *args, **options):
        count = OfficialNews.objects.filter(is_verified=True).filter(rfi_condition()).exclude(drc_condition()).update(is_verified=False)
        self.stdout.write(f'RFI articles outside DRC coverage hidden: {count}')
