from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from unittest.mock import Mock, patch
import time

from django.test import SimpleTestCase, override_settings
from . import services


@override_settings(LLM_PROVIDER='ollama')
class EmbeddingLifecycleTests(SimpleTestCase):
    @override_settings(OLLAMA_MODEL='qwen2.5:7b', OLLAMA_LINGALA_MODEL='congo-lingala:8b')
    @patch.object(services, '_LLM_INSTANCE', None)
    @patch.object(services, '_LINGALA_LLM_INSTANCE', None)
    @patch.object(services, 'ChatOllama')
    def test_only_lingala_uses_specialist_client(self, constructor):
        constructor.side_effect = [Mock(), Mock()]
        general = services.get_chat_ollama('fr')
        lingala = services.get_chat_ollama('ln')
        self.assertIs(services.get_chat_ollama('sw'), general)
        self.assertIs(services.get_chat_ollama('en'), general)
        self.assertIs(services.get_chat_ollama('ln'), lingala)
        self.assertIsNot(lingala, general)
        self.assertEqual([call.kwargs['model'] for call in constructor.call_args_list],
                         ['qwen2.5:7b', 'congo-lingala:8b'])

    @override_settings(OLLAMA_LINGALA_MODEL='')
    @patch.object(services, '_LLM_INSTANCE', None)
    @patch.object(services, 'ChatOllama')
    def test_incomplete_install_keeps_lingala_on_general_model(self, constructor):
        general = services.get_chat_ollama()
        self.assertIs(services.get_chat_ollama('ln'), general)
        constructor.assert_called_once()

    @override_settings(OLLAMA_LINGALA_MODEL='congo-lingala:8b')
    @patch.object(services, 'get_chat_ollama')
    def test_selection_does_not_change_other_conversations(self, client):
        service = services.DRCRagService()
        general = service.llm
        client.return_value = Mock()
        self.assertIs(service.response_model('ln'), client.return_value)
        client.assert_called_with('ln')
        self.assertIs(service.response_model('sw'), general)
        self.assertIs(service.response_model('fr'), general)
        self.assertIs(service.llm, general)

    @override_settings(OLLAMA_MODEL='qwen2.5-coder:14b', OLLAMA_REQUEST_TIMEOUT=300)
    @patch.object(services, '_LLM_INSTANCE', None)
    @patch.object(services, 'ChatOllama')
    def test_chat_client_allows_the_configured_cold_start_timeout(self, model):
        services.get_chat_ollama()
        self.assertEqual(model.call_args.kwargs['model'], 'qwen2.5-coder:14b')
        self.assertEqual(model.call_args.kwargs['client_kwargs']['timeout'], 300)

    @patch.object(services, 'get_embedding_model')
    @patch.object(services, 'get_chat_ollama')
    def test_creating_chat_service_does_not_load_embedding_weights(self, chat, embedding):
        services.DRCRagService()
        embedding.assert_not_called()

    @patch.object(services, '_EMBEDDER_INSTANCE', None)
    @patch.object(services, '_EMBEDDER_RETRY_AT', 0)
    def test_concurrent_queries_load_model_once(self):
        model = Mock()
        def load(*args, **kwargs):
            time.sleep(0.03)
            return model
        constructor = Mock(side_effect=load)
        with patch.dict('sys.modules', {'sentence_transformers': SimpleNamespace(SentenceTransformer=constructor)}):
            with ThreadPoolExecutor(max_workers=6) as pool:
                results = list(pool.map(lambda _: services.get_embedding_model(), range(6)))
        self.assertTrue(all(result is model for result in results))
        constructor.assert_called_once()
        self.assertTrue(constructor.call_args.kwargs['local_files_only'])

    @override_settings(EMBEDDING_ALLOW_DOWNLOAD=False)
    @patch.object(services, '_EMBEDDER_INSTANCE', None)
    @patch.object(services, '_EMBEDDER_RETRY_AT', 0)
    def test_missing_cache_does_not_download_or_retry_every_request(self):
        constructor = Mock(side_effect=RuntimeError('Not cached'))
        with patch.dict('sys.modules', {'sentence_transformers': SimpleNamespace(SentenceTransformer=constructor)}):
            with self.assertLogs(services.logger, level='WARNING'):
                self.assertIsNone(services.get_embedding_model())
                self.assertIsNone(services.get_embedding_model())
        constructor.assert_called_once()
