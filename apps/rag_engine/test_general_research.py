from types import SimpleNamespace
from unittest.mock import Mock, patch
from django.test import TestCase, override_settings
from django.utils import timezone
from .models import OfficialNews, OfficialServiceRegistry
from .services import DRCRagService
from .services import generation_sources
from datetime import timedelta


@override_settings(TAVILY_API_KEY='')
class GeneralResearchTests(TestCase):
    @patch('apps.rag_engine.services.TavilyDRCSearchTool.search', return_value={'status': 'error'})
    @patch('apps.rag_engine.official_portals.find_matching_official_portals', return_value=[])
    def test_specific_headline_wins_over_unrelated_illustrated_news(self, portals, search):
        now = timezone.now()
        exact = OfficialNews.objects.create(title='Le FRN de Joseph Kabila saisit la médiation qatarie contre le projet de changement de Constitution',
            slug='frn-doha', source_name='ACTUALITE.CD', source_url='https://actualite.cd/frn-doha',
            summary='Le FRN intervient auprès du Qatar.', full_content='', published_at=now-timedelta(hours=2))
        OfficialNews.objects.create(title='Une opération contre Ebola dans le Nord-Kivu', slug='ebola',
            source_name='Radio Okapi', source_url='https://www.radiookapi.net/ebola', summary='Un projet de centre de soins.',
            image_url='https://example.cd/photo.jpg', full_content='', published_at=now)
        result = DRCRagService.__new__(DRCRagService).retrieve_context(exact.title)
        news = [s for s in result['sources'] if s.get('source_kind') == 'news']
        self.assertEqual([s['url'] for s in news], [exact.source_url])

    def test_recent_illustrated_articles_guide_generation_without_reviving_old_news(self):
        now = timezone.now()
        fresh = {'title': 'Récent sans photo', 'published_at': now.isoformat(), 'url': 'https://example.cd/a'}
        photo = {'title': 'Récent illustré', 'published_at': (now - timedelta(days=1)).isoformat(), 'image_url': 'https://example.cd/img.jpg', 'url': 'https://example.cd/b'}
        old = {'title': 'Ancien illustré', 'published_at': (now - timedelta(days=60)).isoformat(), 'image_url': 'https://example.cd/old.jpg', 'url': 'https://example.cd/c'}
        self.assertEqual(generation_sources([old, fresh, photo]), [fresh, photo, old])
        prompt = DRCRagService.__new__(DRCRagService).build_prompt_messages('Actualités', 'Texte source', sources=[fresh, photo])[0].content
        self.assertIn('PRIORITÉ DE RÉDACTION', prompt)
        self.assertIn('https://example.cd/b', prompt)

    @patch('apps.rag_engine.services.TavilyDRCSearchTool.search')
    @patch('apps.rag_engine.official_portals.find_matching_official_portals', return_value=[])
    def test_salary_question_reads_media_even_with_several_local_articles(self, portals, search):
        for index in range(2):
            OfficialNews.objects.create(title=f'Soldats : annonce {index}', slug=f'pay-{index}',
                source_name='Radio Okapi', source_url=f'https://www.radiookapi.net/pay-{index}',
                summary='Un article local.', full_content='', published_at=timezone.now())
        search.return_value = {'status': 'success', 'structured': [{
            'title': 'Rémunération selon un média', 'url': 'https://example.com/soldes',
            'snippet': 'Annonce de salaire.', 'raw_content': 'Le montant dépend du grade et de la date.'}]}
        result = DRCRagService.__new__(DRCRagService).retrieve_context("combien l'etat payer les soldat en RDC")
        self.assertEqual(search.call_count, 5)
        self.assertIn('Le montant dépend du grade et de la date.', result['context_text'])
        self.assertTrue(any(source['url'] == 'https://example.com/soldes' for source in result['sources']))

    @patch('apps.rag_engine.services.TavilyDRCSearchTool.search', return_value={'status': 'error'})
    @patch('apps.rag_engine.official_portals.find_matching_official_portals', return_value=[])
    def test_general_latest_news_returns_recent_local_articles(self, portals, search):
        now = timezone.now()
        old = OfficialNews.objects.create(title='Ancien article', slug='old-news', source_name='Source',
            source_url='https://example.org/old', published_at=now-timedelta(days=30))
        recent = OfficialNews.objects.create(title='Nouvel article', slug='new-news', source_name='Source',
            source_url='https://example.org/new', published_at=now-timedelta(hours=1))
        result = DRCRagService.__new__(DRCRagService).retrieve_context('Les dernières actualités en RDC')
        news = [source['url'] for source in result['sources'] if source.get('source_kind') == 'news']
        self.assertEqual(news, [recent.source_url])
        self.assertNotIn(old.source_url, news)
        self.assertEqual(search.call_count, 5)

    def test_prompt_requests_grounded_analysis_when_question_needs_it(self):
        prompt = DRCRagService.__new__(DRCRagService).build_prompt_messages('Que pensez-vous ?', '')[0].content
        self.assertIn('offer a reasoned assessment', prompt)
        self.assertIn('distinguish analysis or', prompt)
        self.assertIn('Prioritize the newest relevant', prompt)

    @patch('apps.rag_engine.official_service_portal.get_official_snapshot', return_value={
        'available': False, 'facts': {}, 'checked_at': ''})
    @patch('apps.rag_engine.services.TavilyDRCSearchTool.search', return_value={'status': 'error'})
    @patch('apps.rag_engine.official_portals.find_matching_official_portals', return_value=[])
    def test_service_directory_match_does_not_stop_web_research(self, portals, search, snapshot):
        OfficialServiceRegistry.objects.create(service_name='Passeport', service_code='passeport',
            institution='Ministère', description='', payment_instructions='',
            official_portal_url='https://example.org/passport')
        result = DRCRagService.__new__(DRCRagService).retrieve_context('Prix du passeport')
        self.assertEqual(search.call_count, 5)
        self.assertTrue(any(source['url'] == 'https://example.org/passport' for source in result['sources']))

    @patch('apps.rag_engine.langgraph_router.classify_query_intent', return_value='research_needed')
    @patch('apps.rag_engine.research_plan.research_queries', return_value=['q1', 'q2', 'q3', 'q4', 'q5'])
    @patch('apps.rag_engine.official_portals.find_matching_official_portals', return_value=[])
    @patch('apps.rag_engine.services.TavilyDRCSearchTool.search')
    def test_researched_answer_streams_and_includes_distinct_search_sources(self, search, portals, plan, classify):
        def result(query, **kwargs):
            return {'status': 'success', 'structured': [{
                'title': 'Source ' + query, 'url': 'https://example.org/' + query,
                'snippet': 'Une information documentée.', 'raw_content': 'Texte de la source.'}]}
        search.side_effect = result
        service = DRCRagService.__new__(DRCRagService)
        service.llm = Mock()
        service.llm.bind.return_value.invoke.return_value.content = '{"relevant_ids": [0, 1, 2, 3, 4]}'
        service.llm.stream.return_value = iter([SimpleNamespace(content='Première '),
                                                SimpleNamespace(content='partie.')])
        events = list(service.stream_query_events('Expliquez le sujet', history=[]))
        self.assertEqual(search.call_count, 5)
        self.assertEqual(len(next(event['sources'] for event in events if event['type'] == 'sources')), 5)
        self.assertEqual([event['token'] for event in events if event['type'] == 'token'],
                         ['Première ', 'partie.'])
        prompt = service.llm.stream.call_args.args[0][0].content
        self.assertIn('https://example.org/q1', prompt)
        self.assertIn('https://example.org/q5', prompt)
