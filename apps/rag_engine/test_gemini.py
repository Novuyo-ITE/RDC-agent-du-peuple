from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase, override_settings
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from .gemini import GeminiChat, get_gemini_chat
from .services import get_chat_ollama, get_llm_provider


class ProviderTests(SimpleTestCase):
    @override_settings(LLM_PROVIDER='auto')
    def test_auto_follows_debug(self):
        with override_settings(DEBUG=True):
            self.assertEqual(get_llm_provider(), 'ollama')
        with override_settings(DEBUG=False):
            self.assertEqual(get_llm_provider(), 'gemini')

    @override_settings(LLM_PROVIDER='gemini', DEBUG=True)
    @patch('apps.rag_engine.gemini.get_gemini_chat')
    @patch('apps.rag_engine.services.ChatOllama')
    def test_explicit_override_and_all_languages_use_gemini(self, ollama, gemini):
        for language in ('fr', 'en', 'ln', 'sw'):
            self.assertIs(get_chat_ollama(language), gemini.return_value)
        ollama.assert_not_called()

    @override_settings(LLM_PROVIDER='invalid')
    def test_invalid_provider_fails(self):
        with self.assertRaises(ImproperlyConfigured):
            get_llm_provider()

    @override_settings(GEMINI_API_KEY='')
    def test_missing_key_fails_clearly(self):
        with self.assertRaisesMessage(ImproperlyConfigured, 'GEMINI_API_KEY'):
            get_gemini_chat()

    @override_settings(LLM_PROVIDER='gemini', TAVILY_API_KEY='test')
    @patch('apps.rag_engine.services.get_chat_ollama')
    @patch('apps.rag_engine.research_plan.ChatOllama')
    def test_planning_uses_gemini(self, ollama, chat):
        from .research_plan import research_queries
        chat.return_value.bind.return_value.invoke.return_value.content = '["a", "b", "c", "d"]'
        self.assertEqual(len(research_queries('Question')), 5)
        chat.return_value.bind.return_value.invoke.assert_called_once()
        ollama.assert_not_called()

    @override_settings(LLM_PROVIDER='gemini')
    @patch('apps.rag_engine.services.get_chat_ollama')
    @patch('langchain_ollama.ChatOllama')
    def test_community_uses_gemini(self, ollama, chat):
        from apps.web_ui.community import model_answer
        chat.return_value.bind.return_value.invoke.return_value.content = 'Answer'
        self.assertEqual(model_answer('Explain', {}), 'Answer')
        ollama.assert_not_called()


class GeminiAdapterTests(SimpleTestCase):
    def setUp(self):
        self.model = GeminiChat(google_api_key='test-not-a-real-key', model='gemini-2.5-flash',
                                vertexai=False, thinking_budget=0, include_thoughts=False)
        self.messages = [SystemMessage(content='Instruction'), HumanMessage(content='Hello'),
                         AIMessage(content='Hi'), HumanMessage(content='More')]

    def test_native_langchain_client(self):
        from langchain_google_genai import ChatGoogleGenerativeAI
        self.assertIsInstance(self.model, ChatGoogleGenerativeAI)

    def test_history_system_instruction_and_json_options(self):
        schema = {'type': 'object', 'properties': {'ids': {'type': 'array', 'items': {'type': 'integer'}}}}
        bound = self.model.bind(format=schema, options={'num_predict': 256, 'temperature': 0, 'num_ctx': 8192})
        request = self.model._prepare_request(self.messages, **bound.kwargs)
        self.assertEqual([m.role for m in request['contents']], ['user', 'model', 'user'])
        config = request['config']
        self.assertEqual(config.system_instruction.parts[0].text, 'Instruction')
        self.assertEqual(config.response_json_schema, schema)
        self.assertEqual(config.response_mime_type, 'application/json')
        self.assertEqual(config.max_output_tokens, 256)
        self.assertEqual(config.temperature, 0)
        self.assertEqual(config.thinking_config.thinking_budget, 0)
        self.assertNotIn('num_ctx', bound.kwargs)

    def test_json_without_schema(self):
        self.assertEqual(self.model.bind(format='json').kwargs,
                         {'response_mime_type': 'application/json'})

    def test_stream_uses_langchain_and_preserves_text(self):
        from langchain_core.messages import AIMessageChunk
        from langchain_core.outputs import ChatGenerationChunk
        def chunks(*args, **kwargs):
            yield ChatGenerationChunk(message=AIMessageChunk(content='Bon'))
            yield ChatGenerationChunk(message=AIMessageChunk(content='jour'))
        with patch.object(GeminiChat, '_stream', chunks):
            self.assertEqual(''.join(c.content for c in self.model.stream(self.messages)), 'Bonjour')
