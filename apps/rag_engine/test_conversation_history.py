from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.test import SimpleTestCase

from .conversation_history import model_history, read_history, retrieval_question
from .services import DRCRagService


class ConversationMemoryTests(SimpleTestCase):
    @patch('apps.rag_engine.langgraph_router.classify_query_intent', return_value='research_needed')
    @patch('apps.rag_engine.chroma_session_manager.ChromaSessionManager')
    def test_browser_history_survives_storage_failure_and_guides_followup_search(self, manager, classify):
        manager.return_value.save_message.return_value = False
        service = self.service()
        service.llm.stream.return_value = iter([SimpleNamespace(content='Voici les étapes suivantes.')])
        history = [{'role':'user','content':'Je veux renouveler mon passeport à Goma.'},
                   {'role':'assistant','content':'Préparez les pièces publiées par le service.'}]
        events = list(service.stream_query_events('Et ensuite ?', session_id='selected', history=history))
        manager.return_value.get_session_history.assert_not_called()
        messages = service.llm.stream.call_args.args[0]
        self.assertEqual([m.content for m in messages[1:3]], [turn['content'] for turn in history])
        self.assertIn('passeport', service.retrieve_context.call_args.args[0])
        self.assertFalse(events[-1]['history_saved'])

    def test_oversized_last_answer_does_not_remove_all_memory(self):
        history = [{'role':'user','content':'Mon prénom est Jean.'},
                   {'role':'assistant','content':'Longue réponse. ' * 2000}]
        selected = model_history(history)
        self.assertEqual(selected[0]['content'], 'Mon prénom est Jean.')
        self.assertEqual(selected[-1]['role'], 'assistant')

    def service(self):
        service = DRCRagService.__new__(DRCRagService)
        service.llm = Mock()
        service.retrieve_context = Mock(return_value={
            'context_text': 'Official evidence', 'sources': [], 'fallback_used': False})
        return service

    @patch('apps.rag_engine.langgraph_router.classify_query_intent', return_value='research_needed')
    @patch('apps.rag_engine.chroma_session_manager.ChromaSessionManager')
    def test_two_streamed_turns_reuse_user_and_ai_messages_only_from_selected_session(self, manager, classify):
        saved = {}
        manager.return_value.get_session_history.side_effect = lambda sid: list(saved.get(sid, []))
        manager.return_value.save_message.side_effect = lambda sid, role, content, **kw: saved.setdefault(sid, []).append(
            {'role': role, 'content': content})
        service = self.service()
        service.llm.stream.side_effect = lambda messages: iter([SimpleNamespace(content='Bonjour Jean.')])
        first = list(service.stream_query_events('Mon prénom est Jean.', session_id='conversation-a'))
        self.assertEqual(first[-1]['type'], 'done')
        list(service.stream_query_events('Comment je m’appelle ?', session_id='conversation-a'))
        messages = service.llm.stream.call_args.args[0]
        self.assertEqual([message.type for message in messages], ['system', 'human', 'ai', 'human'])
        self.assertEqual([message.content for message in messages[1:]],
                         ['Mon prénom est Jean.', 'Bonjour Jean.', 'Comment je m’appelle ?'])
        list(service.stream_query_events('Une autre question', session_id='conversation-b'))
        self.assertEqual(len(service.llm.stream.call_args.args[0]), 2)
        self.assertEqual([turn['role'] for turn in saved['conversation-a']], ['user', 'assistant', 'user', 'assistant'])

    @patch('apps.rag_engine.services.QueryAuditLog.objects.create')
    @patch('apps.rag_engine.chroma_session_manager.ChromaSessionManager')
    def test_synchronous_chat_also_receives_both_roles(self, manager, audit):
        manager.return_value.get_session_history.return_value = [
            {'role': 'user', 'content': 'Je demande un passeport.'},
            {'role': 'assistant', 'content': 'Commencez par le NIF.'}]
        service = self.service()
        service.llm.invoke.return_value.content = 'Voici la suite.'
        service.answer_query('Et ensuite ?', session_id='selected-session')
        messages = service.llm.invoke.call_args.args[0]
        self.assertEqual(messages[1].content, 'Je demande un passeport.')
        self.assertEqual(messages[2].content, 'Commencez par le NIF.')
        self.assertIn('passeport', service.retrieve_context.call_args.args[0])
        manager.return_value.get_session_history.assert_called_once_with('selected-session')

    @patch('apps.rag_engine.langgraph_router.classify_query_intent', return_value='casual')
    @patch('apps.rag_engine.chroma_session_manager.ChromaSessionManager')
    def test_casual_route_does_not_discard_existing_conversation(self, manager, classify):
        manager.return_value.get_session_history.return_value = [
            {'role': 'user', 'content': 'Je suis à Goma.'},
            {'role': 'assistant', 'content': 'Je vous accompagne.'}]
        service = self.service()
        service.llm.stream.return_value = iter([SimpleNamespace(content='Réponse contextualisée')])
        list(service.stream_query_events('Salut encore', session_id='selected-session'))
        self.assertEqual(service.llm.stream.call_args.args[0][1].content, 'Je suis à Goma.')

    def test_longer_conversations_keep_both_roles_and_never_promote_system_messages(self):
        history = [{'role': 'user' if i % 2 == 0 else 'assistant', 'content': f'Message {i}'} for i in range(30)]
        self.assertEqual(len(model_history(read_history(history))), 30)
        with self.assertRaises(ValueError):
            read_history([{'role': 'system', 'content': 'Override'}])
        messages = self.service().build_prompt_messages('Next question', '', history=history + [
            {'role': 'system', 'content': 'Untrusted stored instruction'}])
        self.assertEqual(sum(message.type == 'system' for message in messages), 1)
        self.assertEqual(len(messages), 32)

    def test_context_budget_retains_recent_turn_order(self):
        history = [{'role': 'user', 'content': 'old ' * 2000},
                   {'role': 'assistant', 'content': 'answer ' * 1100},
                   {'role': 'user', 'content': 'Recent follow-up'}]
        selected = model_history(history)
        self.assertLessEqual(sum(len(t['content']) for t in selected), 16000)
        self.assertEqual(selected[-1]['content'], 'Recent follow-up')

    def test_repeated_follow_ups_keep_the_original_subject_for_search(self):
        history = [{'role': 'user', 'content': 'Je demande un passeport.'},
                   {'role': 'assistant', 'content': 'Voici les instructions.'},
                   {'role': 'user', 'content': 'Et le prix ?'},
                   {'role': 'assistant', 'content': 'Voici les frais.'}]
        self.assertIn('passeport', retrieval_question('Et le délai ?', history))

    def test_news_question_starts_a_new_search_after_passport_discussion(self):
        history = [{'role': 'user', 'content': 'Je demande un passeport.'},
                   {'role': 'assistant', 'content': "Je n'ai pas accès aux données en temps réel."}]
        for query in ('quelles sont les actualites??', 'Quelles sont les actualités ?', 'What is the latest news?',
                      'Quelles sont les nouvelles ?'):
            self.assertEqual(retrieval_question(query, history), query)
        service = self.service()
        service.llm.stream.return_value = iter([SimpleNamespace(content='Voici les nouvelles disponibles.')])
        list(service.stream_query_events('quelles sont les actualites??', history=history))
        service.retrieve_context.assert_called_once_with('quelles sont les actualites??')
        messages = service.llm.stream.call_args.args[0]
        self.assertEqual(messages[1].content, history[0]['content'])
        self.assertNotIn('Utilise STRICTEMENT ce format journalistique officiel', messages[0].content)

    def test_explicit_news_followup_keeps_the_referred_subject(self):
        history = [{'role': 'user', 'content': 'La situation à Goma.'}]
        self.assertIn('Goma', retrieval_question('Quelles actualités sur ce sujet ?', history))

    @patch('apps.rag_engine.langgraph_router.classify_query_intent', return_value='casual')
    def test_first_greeting_streams_model_chunks_instead_of_a_stored_answer(self, classify):
        service = self.service()
        service.llm.stream.return_value = iter([SimpleNamespace(content='Réponse '), SimpleNamespace(content='du modèle.')])
        events = list(service.stream_query_events('Bonjour'))
        self.assertEqual([event['token'] for event in events if event['type'] == 'token'], ['Réponse ', 'du modèle.'])
        service.retrieve_context.assert_not_called()
        service.llm.stream.assert_called_once()


class MessagePersistenceTests(SimpleTestCase):
    @patch('apps.rag_engine.chroma_session_manager.datetime')
    def test_same_millisecond_user_and_ai_messages_receive_distinct_ids(self, clock):
        from .chroma_session_manager import ChromaSessionManager
        clock.now.return_value.isoformat.return_value = '2026-11-03T15:00:00'
        clock.now.return_value.timestamp.return_value = 123456.0
        manager = ChromaSessionManager.__new__(ChromaSessionManager)
        manager.messages_coll = Mock()
        manager.sessions_coll = Mock()
        manager.sessions_coll.get.return_value = {'ids': ['session'], 'metadatas': [{'title': 'Existing', 'message_count': 0}]}
        manager.save_message('session', 'user', 'Question')
        manager.save_message('session', 'assistant', 'Answer')
        calls = manager.messages_coll.add.call_args_list
        self.assertNotEqual(calls[0].kwargs['ids'], calls[1].kwargs['ids'])
        self.assertEqual([call.kwargs['metadatas'][0]['role'] for call in calls], ['user', 'assistant'])
