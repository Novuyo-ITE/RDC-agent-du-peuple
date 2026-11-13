"""Select news about public services without presenting unrelated headlines as such."""
from functools import reduce
from operator import or_

from django.db.models import Q
from django.utils import timezone

from apps.rag_engine.models import OfficialNews


PUBLIC_SERVICE_TERMS = (
    'service public', 'services publics', 'administration publique', 'fonction publique',
    'passeport', 'permis de conduire', 'acte de naissance', 'état civil', 'etat civil',
    'carte d’identité', "carte d'identité", 'carte nationale d’identité',
    'immatriculation', 'guichet unique', 'visa', 'démarche administrative',
    'démarches administratives', 'formalité administrative', 'procédure administrative',
    'impôt', 'impot', 'fiscal', 'taxe', 'facture normalisée', 'sécurité sociale',
    'cnss', 'assurance maladie', 'transport public', 'code de la route',
)


def recent_service_news(limit=5):
    conditions = (Q(title__icontains=term) | Q(summary__icontains=term)
                  for term in PUBLIC_SERVICE_TERMS)
    return OfficialNews.objects.approved().filter(
        reduce(or_, conditions), published_at__lte=timezone.now()
    ).order_by('-published_at', '-pk')[:limit]
