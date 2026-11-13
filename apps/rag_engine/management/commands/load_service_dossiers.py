"""Import reviewed source data; no network calls or invented model-generated facts."""
import json
from pathlib import Path
from urllib.parse import urlsplit

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from apps.rag_engine.models import OfficialServiceRegistry


class Command(BaseCommand):
    help = 'Load reviewed official service dossiers, including form availability and source links.'

    def add_arguments(self, parser):
        parser.add_argument('--file', type=Path, default=settings.BASE_DIR / 'apps/rag_engine/data/service_dossiers.json')

    @transaction.atomic
    def handle(self, *args, **options):
        dossiers = json.loads(options['file'].read_text(encoding='utf-8'))
        for code, dossier in dossiers.items():
            references = dossier['references']
            if not references or not dossier.get('reviewed_at'):
                raise CommandError(f'Missing dated evidence: {code}')
            for url in references + [r['url'] for r in dossier['form_resources']]:
                if urlsplit(url).scheme != 'https' or not urlsplit(url).hostname:
                    raise CommandError(f'Invalid source: {code}')
            facts = {}
            for key, value in dossier['facts'].items():
                url = dossier.get('fact_sources', {}).get(key, dossier['source_url'])
                if url not in references:
                    raise CommandError(f'Unreferenced fact: {code}/{key}')
                def fact(text):
                    return {'text': text, 'url': url, 'kind': 'reviewed_summary'}
                facts[key] = [fact(text) for text in value] if isinstance(value, list) else fact(value)
            snapshot = {
                'source_url': dossier['source_url'], 'available': True,
                'checked_at': dossier['reviewed_at'], 'provenance': 'reviewed_official_sources',
                'facts': facts, 'steps': [f['text'] for f in facts['steps']],
                'forms': dossier.get('forms', []), 'form_resources': dossier['form_resources'],
                'references': references, 'notes': dossier.get('notes', []),
                'text': '',
            }
            count = OfficialServiceRegistry.objects.filter(service_code=code).update(
                source_snapshot=snapshot, official_portal_url=dossier['source_url'])
            if not count:
                raise CommandError(f'Service missing from registry: {code}. Seed the service directory first.')
            self.stdout.write(f'Loaded {code}: {len(facts["steps"])} steps, {len(snapshot["form_resources"])} resources')
