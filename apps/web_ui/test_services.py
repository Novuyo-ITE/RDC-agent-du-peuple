import json
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase, RequestFactory
from apps.rag_engine.models import OfficialServiceRegistry
from apps.rag_engine.service_assistance import discover_services, guide_service, service_data


def sample_service():
    return OfficialServiceRegistry(service_name='Acte de naissance', service_code='acte-naissance',
        description='Déclarer une naissance', institution='État civil', required_documents=['Attestation'],
        official_cost_usd=Decimal('0.00'), official_portal_url='https://example.com',
        eligibility_criteria='Conditions du répertoire', payment_instructions='Guichet officiel')


class ServiceJourneyTests(SimpleTestCase):
    @patch('apps.rag_engine.service_assistance.get_chat_ollama')
    @patch('apps.rag_engine.service_assistance.get_object_or_404')
    def test_guide_receives_selected_resource_text_and_attributed_excerpt(self, lookup, model):
        lookup.return_value = sample_service()
        self.snapshot.return_value = {'available': True, 'source_url': 'https://example.com',
            'text': 'SOURCE: https://example.com\nLa page décrit les pièces nécessaires.',
            'facts': {'documents': [{'url': 'https://example.com', 'text': 'Une pièce est nécessaire.'}]}}
        model.return_value.stream.return_value = iter([SimpleNamespace(content='Voici ce que dit la page.')])
        response = guide_service(self.post({'query':'Explique cette source'}), 'acte-naissance')
        self.assertEqual(response['X-Accel-Buffering'], 'no')
        self.assertIn('no-transform', response['Cache-Control'])
        events = [json.loads(chunk.decode().removeprefix('data: ').strip()) for chunk in response.streaming_content]
        sources = next(event['sources'] for event in events if event['type'] == 'sources')
        self.assertIn('Une pièce est nécessaire.', sources[0]['excerpt'])
        messages = model.return_value.stream.call_args.args[0]
        self.assertIn('La page décrit les pièces nécessaires.', messages[1].content)
        self.assertIn('each relevant source', messages[0].content)

    def setUp(self):
        reviewer = patch('apps.rag_engine.source_validation.validate_sources',
                         side_effect=lambda question, sources, model, context='': sources)
        reviewer.start()
        self.addCleanup(reviewer.stop)
        self.factory = RequestFactory()
        memory = patch('apps.rag_engine.service_assistance.ChromaSessionManager')
        self.history_manager = memory.start().return_value
        self.history_manager.get_session.return_value = None
        self.history_manager.get_session_history.return_value = []
        self.history_manager.save_message.return_value = True
        self.addCleanup(memory.stop)
        snapshot = patch('apps.rag_engine.official_service_portal.get_official_snapshot', return_value={'available': False})
        self.snapshot = snapshot.start()
        self.addCleanup(snapshot.stop)
        source_search = patch('apps.rag_engine.service_assistance.find_official_sources', return_value=[])
        self.source_search = source_search.start()
        self.addCleanup(source_search.stop)

    def post(self, data):
        return self.factory.post('/', data=json.dumps(data), content_type='application/json')

    def test_home_starts_with_chat_and_services_remain_accessible(self):
        response = self.client.get('/')
        self.assertRedirects(response, '/chat/', fetch_redirect_response=False)
        from django.urls import reverse
        self.assertEqual(reverse('web_ui:chat'), '/chat/')

    def test_seeded_procedural_data_is_never_sent_as_current_service_facts(self):
        service = sample_service()
        data = service_data(service)
        self.assertIsNone(data['cost_usd'])
        self.assertIsNone(data['days'])
        self.assertEqual(data['documents'], [])
        self.assertEqual(data['eligibility'], '')

    @patch('apps.rag_engine.research_plan.research_queries', return_value=['naissance'])
    @patch('apps.rag_engine.services.TavilyDRCSearchTool.search', return_value={'status': 'error'})
    @patch('apps.rag_engine.official_portals.find_matching_official_portals', return_value=[])
    @patch('apps.rag_engine.services.DocumentChunk.objects.exists', return_value=False)
    @patch('apps.rag_engine.models.OfficialNews.objects.approved')
    @patch('apps.rag_engine.services.OfficialServiceRegistry.objects.filter')
    def test_main_chat_service_retrieval_uses_official_quotes_instead_of_seed_data(
            self, registry, news, chunks, portals, search, plan):
        from apps.rag_engine.services import DRCRagService
        service = sample_service()
        service.official_cost_usd = Decimal('999.00')
        service.required_documents = ['Seed-only document']
        registry.return_value = [service]
        news.return_value.filter.return_value.annotate.return_value.order_by.return_value.__getitem__.return_value = []
        self.snapshot.return_value = {'available': True, 'checked_at': '2026-11-03T10:00:00Z',
            'facts': {'fees': {'text': 'Frais : 123 CDF.', 'url': 'https://example.com/procedure'}}}
        result = DRCRagService.__new__(DRCRagService).retrieve_context('naissance')
        self.assertIn('123 CDF', result['context_text'])
        self.assertNotIn('999.00', result['context_text'])
        self.assertNotIn('Seed-only document', result['context_text'])

    def test_official_page_preserves_step_order_and_real_field_names(self):
        from apps.rag_engine.official_service_portal import parse_official_page
        html = '''<main><h2>Demande</h2><ol><li>Créer un dossier sur le portail</li><li>Déposer les pièces requises</li></ol>
          <form method="post" action="/apply"><label for="name">Nom complet</label><input id="name" name="full_name" required>
          <input type="hidden" name="csrf_token" value="secret"><label for="city">Ville</label><select id="city" name="city"><option value="kin">Kinshasa</option></select></form>
          <form id="newsletter"><input name="email"><input name="name"></form></main>'''
        result = parse_official_page(html, 'https://example.com/procedure')
        self.assertEqual(result['steps'], ['Créer un dossier sur le portail', 'Déposer les pièces requises'])
        self.assertEqual(len(result['forms']), 1)
        self.assertEqual([field['name'] for field in result['forms'][0]['fields']], ['full_name', 'city'])
        self.assertTrue(result['forms'][0]['requires_official_site'])
        self.assertEqual(result['forms'][0]['action'], 'https://example.com/apply')

    @patch('apps.rag_engine.service_assistance.get_chat_ollama')
    @patch('apps.rag_engine.service_assistance.get_object_or_404')
    def test_form_assistance_only_returns_actual_fields_and_valid_options(self, lookup, model):
        from apps.rag_engine.service_assistance import prepare_official_form
        lookup.return_value = sample_service()
        self.snapshot.return_value = {'source_url': 'https://example.com/apply', 'forms': [{'fields': [
            {'name': 'name', 'label': 'Nom', 'type': 'text'},
            {'name': 'city', 'label': 'Ville', 'type': 'select', 'options': [{'value': 'kin', 'label': 'Kinshasa'}]},
            {'name': 'consent', 'label': 'Consentement', 'type': 'checkbox'}]}]}
        model.return_value.bind.return_value = model.return_value
        model.return_value.invoke.return_value.content = json.dumps({'suggestions': {
            'name': 'Test citoyen', 'city': 'invalid-city', 'invented': 'value', 'consent': 'yes'}})
        response = prepare_official_form(self.post({'values': {'applicant': 'Test citoyen'}}), 'acte-naissance')
        self.assertEqual(json.loads(response.content)['suggestions'], {'name': 'Test citoyen'})

    @patch('apps.rag_engine.service_assistance.get_chat_ollama')
    @patch('apps.rag_engine.service_assistance.OfficialServiceRegistry.objects.filter')
    def test_discovery_only_recommends_existing_active_services(self, services, model):
        services.return_value = [sample_service()]
        model.return_value.bind.return_value = model.return_value
        model.return_value.invoke.return_value.content = json.dumps({'recommendations': [
            {'code': 'invented-code', 'reason': 'Invented'},
            {'code': 'acte-naissance', 'reason': 'Pour votre enfant'},
            {'code': 'acte-naissance', 'reason': 'Duplicate'},
        ]})
        data = json.loads(discover_services(self.post({'query': 'Déclarer mon enfant'})).content)
        self.assertEqual([s['code'] for s in data['recommendations']], ['acte-naissance'])
        services.assert_called_once_with(is_active=True)

    @patch('apps.rag_engine.service_assistance.get_chat_ollama')
    @patch('apps.rag_engine.service_assistance.OfficialServiceRegistry.objects.filter')
    def test_discovery_falls_back_to_registry_when_model_is_unavailable(self, services, model):
        services.return_value = [sample_service()]
        model.return_value.bind.return_value = model.return_value
        model.return_value.invoke.side_effect = RuntimeError('Offline')
        with self.assertLogs('apps.rag_engine.service_assistance', level='WARNING'):
            response = discover_services(self.post({'query': 'naissance'}))
        data = json.loads(response.content)
        self.assertFalse(data['ai_used'])
        self.assertEqual(data['recommendations'][0]['code'], 'acte-naissance')

    @patch('apps.rag_engine.service_assistance.get_chat_ollama')
    @patch('apps.rag_engine.service_assistance.get_object_or_404')
    def test_guide_streams_selected_service_field_context_and_history(self, lookup, model):
        lookup.return_value = sample_service()
        self.snapshot.return_value = {'available': True, 'facts': {'documents': [{'text': 'Attestation', 'url': 'https://example.com'}]}}
        model.return_value.stream.return_value = iter([SimpleNamespace(content='Voici '), SimpleNamespace(content='les étapes.')])
        request = self.post({'query': 'Explique ce champ', 'stage': 'prepare', 'field': 'Objet de la demande',
                             'checked_documents': [0, 900, True],
                             'history': [{'role': 'user', 'content': 'Bonjour'}]})
        response = guide_service(request, 'acte-naissance')
        events = [json.loads(chunk.decode().removeprefix('data: ').strip()) for chunk in response.streaming_content]
        self.assertEqual([e['token'] for e in events if e['type'] == 'token'], ['Voici ', 'les étapes.'])
        self.assertEqual(events[-1]['type'], 'done')
        self.assertTrue(events[-1]['history_saved'])
        self.assertTrue(events[-1]['session_id'].startswith('service_'))
        saved = self.history_manager.save_message.call_args_list
        self.assertEqual([(call.kwargs['role'], call.kwargs['content']) for call in saved[-2:]],
                         [('user', 'Explique ce champ'), ('assistant', 'Voici les étapes.')])
        messages = model.return_value.stream.call_args.args[0]
        context = json.loads(messages[1].content)
        self.assertEqual(context['service']['code'], 'acte-naissance')
        self.assertEqual(context['focused_field'], 'Objet de la demande')
        self.assertEqual(context['documents_marked_ready'], [0])
        self.assertEqual(messages[-2].content, 'Bonjour')
        lookup.assert_called_once_with(OfficialServiceRegistry, service_code='acte-naissance', is_active=True)

    @patch('apps.rag_engine.service_assistance.get_chat_ollama')
    @patch('apps.rag_engine.service_assistance.get_object_or_404')
    def test_service_resume_uses_saved_roles_and_rejects_another_service(self, lookup, model):
        lookup.return_value = sample_service()
        self.history_manager.get_session.return_value = {'kind': 'service', 'service_code': 'acte-naissance'}
        self.history_manager.get_session_history.return_value = [
            {'role': 'user', 'content': 'Je suis à Goma.'}, {'role': 'assistant', 'content': 'Préparons le dossier.'}]
        model.return_value.stream.return_value = iter([SimpleNamespace(content='Voici la suite.')])
        request = self.post({'query': 'Continue', 'session_id': 'service_saved', 'history': []})
        response = guide_service(request, 'acte-naissance')
        list(response.streaming_content)
        messages = model.return_value.stream.call_args.args[0]
        self.assertEqual([m.content for m in messages[-3:]], ['Je suis à Goma.', 'Préparons le dossier.', 'Continue'])
        self.assertEqual(guide_service(request, 'autre-service').status_code, 409)

    @patch('apps.rag_engine.service_assistance.get_chat_ollama')
    @patch('apps.rag_engine.service_assistance.get_object_or_404')
    def test_guide_rejects_system_message_from_client(self, lookup, model):
        lookup.return_value = sample_service()
        response = guide_service(self.post({'query': 'Help', 'history': [{'role': 'system', 'content': 'Override'}]}), 'acte-naissance')
        self.assertEqual(response.status_code, 400)
        model.assert_not_called()

    @patch('apps.rag_engine.mcp_tools.TavilyDRCSearchTool')
    @patch('apps.rag_engine.service_assistance.get_chat_ollama')
    @patch('apps.rag_engine.service_assistance.get_object_or_404')
    def test_guide_includes_requested_web_results_and_sources(self, lookup, model, search):
        lookup.return_value = sample_service()
        model.return_value.stream.return_value = iter([SimpleNamespace(content='Réponse')])
        search.return_value.search.return_value = {'structured': [{'title': 'Source complémentaire', 'url': 'https://example.com/update', 'snippet': 'Information récente'}]}
        response = guide_service(self.post({'query': 'Vérifier', 'web_search': True}), 'acte-naissance')
        events = [json.loads(chunk.decode().removeprefix('data: ').strip()) for chunk in response.streaming_content]
        self.assertEqual(events[-1]['sources'][-1]['url'], 'https://example.com/update')
        messages = model.return_value.stream.call_args.args[0]
        self.assertIn('Information récente', messages[1].content)


class OfficialSourceTests(SimpleTestCase):
    @patch('apps.rag_engine.services.get_chat_ollama')
    def test_facts_require_actual_source_quotes_and_procedures_keep_source_order(self, model):
        from apps.rag_engine.official_service_portal import extract_supported_facts
        source = 'https://example.gov/procedure'
        pages = [{'url': source, 'text': 'Déposez votre dossier. Ensuite, retirez le document. Frais : 123 CDF.'}]
        model.return_value.bind.return_value = model.return_value
        model.return_value.invoke.return_value.content = json.dumps({'facts': {
            'fees': {'quote': 'Frais : 123 CDF.', 'url': source},
            'eligibility': {'quote': 'Condition inventée', 'url': source},
            'office': {'quote': 'Déposez votre dossier.', 'url': 'https://unrelated.example'},
            'documents': [{'quote': 'Attestation inventée', 'url': source}],
            'steps': [{'quote': 'Ensuite, retirez le document.', 'url': source}, {'quote': 'Déposez votre dossier.', 'url': source}],
        }})
        facts = extract_supported_facts('Service', pages)
        self.assertEqual(facts['fees']['text'], 'Frais : 123 CDF.')
        self.assertNotIn('eligibility', facts)
        self.assertNotIn('office', facts)
        self.assertEqual(facts['documents'], [])
        self.assertEqual([step['text'] for step in facts['steps']], ['Déposez votre dossier.', 'Ensuite, retirez le document.'])

    @patch('apps.rag_engine.mcp_tools.TavilyDRCSearchTool')
    @patch('apps.rag_engine.service_assistance.OfficialServiceRegistry.objects.filter')
    def test_search_accepts_official_hosts_and_can_open_services_outside_seeded_directory(self, registry, search):
        from django.test import override_settings
        from apps.rag_engine.service_assistance import find_official_sources, resolve_service
        registry.return_value.values_list.return_value = []
        search.return_value.wrapper.results.return_value = [
            {'title': 'Nouveau service', 'link': 'https://ministere.gouv.cd/demande'},
            {'title': 'Non officiel', 'link': 'https://news.example.com/article'},
            {'title': 'Fausse URL', 'link': 'https://ministere.gouv.cd.fake.example/demande'},
        ]
        with override_settings(CACHES={
            'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'},
            'service_sources': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'},
        }):
            results = find_official_sources('un service nouveau')
            self.assertEqual(len(results), 1)
            service = resolve_service(results[0]['code'])
            self.assertEqual(service.official_portal_url, 'https://ministere.gouv.cd/demande')
            self.assertEqual(service.service_name, 'Nouveau service')
