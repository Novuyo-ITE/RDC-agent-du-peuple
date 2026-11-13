import sys
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, patch

from apps.voice import audio_utils


class WhisperModelTests(TestCase):
    def test_cpu_fallback_keeps_the_default_medium_model(self):
        calls = []
        cpu_model = object()

        def load_model(name, **kwargs):
            calls.append((name, kwargs))
            if kwargs['device'] == 'cuda':
                raise RuntimeError('CUDA unavailable')
            return cpu_model

        with patch.object(audio_utils, '_WHISPER_MODEL', None), \
             patch.dict('os.environ', {'WHISPER_DEVICE': 'cuda'}, clear=True), \
             patch.dict(sys.modules, {'faster_whisper': SimpleNamespace(WhisperModel=load_model)}):
            self.assertIs(audio_utils.get_whisper_model(), cpu_model)

        self.assertEqual(calls[-1][0], 'medium')
        self.assertEqual(calls[-1][1]['device'], 'cpu')

    def test_french_is_passed_to_the_transcription_model(self):
        model = Mock()
        model.transcribe.return_value = ([SimpleNamespace(text=' Bonjour', avg_logprob=-0.1)],
                                         SimpleNamespace(language='fr'))
        with patch.object(audio_utils, 'get_whisper_model', return_value=model):
            result = audio_utils.transcribe_audio_bytes(b'audio', language='fr')

        self.assertEqual(result['text'], 'Bonjour')
        self.assertEqual(model.transcribe.call_args.kwargs['language'], 'fr')
