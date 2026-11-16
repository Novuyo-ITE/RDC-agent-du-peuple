"""Hero examples copied from the same sourced dossiers as service pages."""
from urllib.parse import urlsplit
from django.urls import reverse
from apps.rag_engine.models import OfficialServiceRegistry

QUESTIONS = {
    'passeport-biometrique-ordinaire': 'Comment demander un passeport en RDC ?',
    'creation-entreprise-guce': 'Comment créer une entreprise en RDC ?',
    'acte-de-naissance-etat-civil': 'Comment obtenir un acte de naissance ?',
}


def landing_service_examples():
    services = {service.service_code: service for service in
                OfficialServiceRegistry.objects.filter(is_active=True, service_code__in=QUESTIONS)
                .only('service_code', 'source_snapshot')}
    examples = []
    for code, question in QUESTIONS.items():
        service = services.get(code)
        if not service:
            continue
        snapshot = service.source_snapshot or {}
        facts = snapshot.get('facts', {})
        steps = facts.get('steps', []) if isinstance(facts, dict) else []
        # Preserve the entire recorded sequence; never silently omit an unsourced step.
        if not isinstance(steps, list) or not steps:
            continue
        if any(not isinstance(step, dict) or not step.get('text') or
               urlsplit(step.get('url', '')).scheme not in ('http', 'https') or
               not urlsplit(step.get('url', '')).netloc for step in steps):
            continue
        sources = list(dict.fromkeys(step['url'] for step in steps))
        examples.append({
            'question': question,
            'answer': 'Voici les étapes indiquées dans la fiche documentée :\n\n' +
                      '\n\n'.join(f"{i}. {step['text']}" for i, step in enumerate(steps, 1)),
            'sources': sources,
            'checkedAt': snapshot.get('checked_at', ''),
            'href': reverse('web_ui:service_workspace', kwargs={'service_code': code}),
            'link': 'Consulter la fiche et ses sources',
        })
    return examples
