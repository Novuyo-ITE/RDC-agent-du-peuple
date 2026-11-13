"""Register legal services with official source links, without assumed fees or deadlines."""
from django.core.management.base import BaseCommand
from django.db import transaction
from apps.rag_engine.models import OfficialServiceRegistry, ServiceCategory


LEGAL_SERVICES = [
    {
        'service_code': 'extrait-casier-judiciaire',
        'service_name': 'Extrait de casier judiciaire',
        'description': 'Demander un extrait de casier judiciaire auprès du service judiciaire compétent.',
        'institution': 'Services judiciaires compétents / Ministère de la Justice',
        'official_portal_url': 'https://servicepublic.gouv.cd/service/326',
    },
    {
        'service_code': 'certificat-nationalite-congolaise',
        'service_name': 'Certificat de nationalité congolaise',
        'description': 'S’orienter vers la démarche de délivrance d’un certificat de nationalité congolaise.',
        'institution': 'Ministère de la Justice et Garde des Sceaux',
        'official_portal_url': 'https://servicepublic.gouv.cd/service/462',
    },
    {
        'service_code': 'certification-authentification-legalisation-signature',
        'service_name': 'Certification, authentification et légalisation de signature',
        'description': 'Identifier la démarche adaptée pour faire certifier un document, authentifier un acte ou légaliser une signature.',
        'institution': 'Ministère de la Justice et Garde des Sceaux',
        'official_portal_url': 'https://servicepublic.gouv.cd/service/423',
    },
]


class Command(BaseCommand):
    help = 'Add legal services from the official public service catalog.'

    @transaction.atomic
    def handle(self, *args, **options):
        for entry in LEGAL_SERVICES:
            service, created = OfficialServiceRegistry.objects.get_or_create(
                service_code=entry['service_code'],
                defaults={**entry, 'category': ServiceCategory.JUSTICE_SECURITY,
                          'processing_time_days': None, 'official_cost_usd': None,
                          'official_cost_cdf': None, 'payment_instructions': '',
                          'required_documents': [], 'is_active': True},
            )
            self.stdout.write(f"{'Added' if created else 'Already registered'}: {service.service_code}")
