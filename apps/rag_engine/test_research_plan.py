from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.test import SimpleTestCase, override_settings

from .research_plan import merge_web_results, research_queries, search_perspectives
from .langgraph_router import classify_query_intent


@override_settings(LLM_PROVIDER='ollama')
class ResearchPlanTests(SimpleTestCase):
    def test_greeting_followed_by_factual_question_still_gets_research(self):
        self.assertEqual(classify_query_intent('Bonjour, combien gagnent les soldats ?'), 'research_needed')
        self.assertEqual(classify_query_intent('Bonjour !'), 'casual')
        self.assertEqual(classify_query_intent('Merci beaucoup'), 'casual')

    @override_settings(TAVILY_API_KEY='test', OLLAMA_KEEP_ALIVE='24h', OLLAMA_NUM_CTX=8192, OLLAMA_REQUEST_TIMEOUT=300)
    @patch('apps.rag_engine.research_plan.ChatOllama')
    def test_step_back_planner_keeps_original_question_and_four_perspectives(self, model):
        model.return_value.invoke.return_value = SimpleNamespace(content=(
            '["principes des salaires militaires en RDC", "soldes militaires RDC données", '
            '"analyses salaires FARDC", "actualités rémunération FARDC"]'))
        queries = research_queries('Quel est le salaire des soldats ?')
        self.assertEqual(model.call_args.kwargs['keep_alive'], '24h')
        self.assertEqual(model.call_args.kwargs['num_ctx'], 8192)
        self.assertEqual(model.call_args.kwargs['client_kwargs']['timeout'], 300)
        self.assertEqual(len(queries), 5)
        self.assertEqual(queries[0], 'Quel est le salaire des soldats ?')
        self.assertIn('principes', queries[1])
        prompt = model.return_value.invoke.call_args.args[0]
        self.assertIn('step-back', prompt[0].content)
        self.assertEqual(prompt[1].content, queries[0])

    @override_settings(TAVILY_API_KEY='test')
    @patch('apps.rag_engine.research_plan.ChatOllama')
    def test_invalid_model_plan_falls_back_to_five_distinct_searches(self, model):
        model.return_value.invoke.return_value = SimpleNamespace(content='not JSON')
        queries = research_queries('Question')
        self.assertEqual(len(queries), 5)
        self.assertEqual(len(set(queries)), 5)
        self.assertTrue(all('Question' in query for query in queries))

    @override_settings(TAVILY_API_KEY='')
    def test_news_fallback_searches_for_recent_reports_instead_of_abstract_principles(self):
        from django.utils import timezone
        queries = research_queries('quelles sont les actualites??')
        self.assertEqual(len(queries), 5)
        for query in queries[1:]:
            self.assertIn('RDC', query)
            self.assertIn(timezone.localdate().isoformat(), query)
            self.assertNotIn('principes', query)

    def test_new_identity_document_still_uses_the_administrative_prompt(self):
        from .news_answers import news_question
        from .services import DRCRagService
        question = "Comment obtenir une nouvelle carte d'identité ?"
        self.assertFalse(news_question(question))
        prompt = DRCRagService.__new__(DRCRagService).build_prompt_messages(question, '')[0].content
        self.assertIn('POUR LES DÉMARCHES ADMINISTRATIVES', prompt)

    def test_partial_search_failures_do_not_lose_other_results(self):
        def search(query, **kwargs):
            if query == 'failed':
                raise RuntimeError('offline')
            return {'status': 'success', 'structured': [{'url': 'https://example.org/' + query}]}
        searcher = Mock(search=search)
        results, social = search_perspectives(searcher, ['first', 'failed', 'third'])
        self.assertEqual([item.get('status') for item in results], ['success', None, 'success'])
        self.assertEqual(social, [])

    def test_passport_searches_always_include_drc_context(self):
        searcher = Mock()
        searcher.search.return_value = {'status': 'success', 'structured': []}
        search_perspectives(searcher, ['demarches passeport ou tenant lieu', 'passport requirements'])
        self.assertEqual(searcher.search.call_count, 2)
        self.assertTrue(all(call.kwargs['drc_context'] for call in searcher.search.call_args_list))

    def test_scope_is_present_even_with_brussels_source_or_previous_answer(self):
        from .services import DRCRagService
        from .conversation import conversation_messages
        from .geographic_scope import DRC_SCOPE_INSTRUCTIONS

        question = 'Quelles sont les demarches pour obtenir un passeport ou tenant lieu'
        history = [{'role': 'assistant', 'content': 'Allez a Bruxelles.'}]
        messages = DRCRagService.__new__(DRCRagService).build_prompt_messages(
            question, 'Ambassade a Bruxelles : capture biometrique au Benelux.', history=history)
        self.assertIn(DRC_SCOPE_INSTRUCTIONS, messages[0].content)
        self.assertIn(DRC_SCOPE_INSTRUCTIONS, conversation_messages(question, history=history)[0].content)
        self.assertIn('only consular sources', messages[0].content)
        self.assertIn('when explicitly requested', messages[0].content)

    def test_merge_interleaves_perspectives_deduplicates_and_excludes_x(self):
        results = [
            {'status': 'success', 'structured': [
                {'url': 'https://example.org/a'}, {'url': 'https://example.org/b'}]},
            {'status': 'success', 'structured': [
                {'url': 'https://example.org/a#section'}, {'url': 'https://other.org/c'},
                {'url': 'https://x.com/account/status/123'}]},
        ]
        self.assertEqual([item['url'] for item in merge_web_results(results)],
                         ['https://example.org/a', 'https://example.org/b', 'https://other.org/c'])
