from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase, override_settings

from apps.web_ui.community import model_answer


@override_settings(LLM_PROVIDER='ollama')
class CommunityOllamaLifetimeTests(SimpleTestCase):
    @override_settings(OLLAMA_KEEP_ALIVE='24h', OLLAMA_MODEL='test-model', OLLAMA_NUM_CTX=8192)
    @patch('langchain_ollama.ChatOllama')
    def test_community_requests_keep_the_configured_model_loaded(self, model):
        model.return_value.invoke.return_value = SimpleNamespace(content='Réponse')
        self.assertEqual(model_answer('Explique.', {'text': 'Source'}), 'Réponse')
        self.assertEqual(model.call_args.kwargs['keep_alive'], '24h')
        self.assertEqual(model.call_args.kwargs['model'], 'test-model')
        self.assertEqual(model.call_args.kwargs['num_ctx'], 8192)
