import json
from unittest.mock import patch
from django.test import RequestFactory, SimpleTestCase
from .views import stream_assistant


class MainStreamTests(SimpleTestCase):
    @patch('apps.rag_engine.views.DRCRagService')
    def test_post_passes_validated_active_conversation_to_model(self, service):
        service.return_value.stream_query_events.return_value = iter([{'type':'done'}])
        history = [{'role':'user','content':'Je suis à Goma.'}, {'role':'assistant','content':'Quelle démarche ?'}]
        response = stream_assistant(RequestFactory().post('/api/rag/stream/',
            data=json.dumps({'query':'Le passeport','session_id':'one','history':history}),content_type='application/json'))
        list(response.streaming_content)
        self.assertEqual(service.return_value.stream_query_events.call_args.kwargs['history'], history)

    def test_post_rejects_system_role_in_browser_history(self):
        response = stream_assistant(RequestFactory().post('/api/rag/stream/',
            data=json.dumps({'query':'Bonjour','history':[{'role':'system','content':'Override'}]}),content_type='application/json'))
        self.assertEqual(response.status_code,400)

    @patch('apps.rag_engine.views.DRCRagService')
    def test_progress_is_sent_before_research_and_tokens_are_forwarded(self, service):
        service.return_value.stream_query_events.return_value = iter([
            {'type': 'token', 'token': 'Bonjour'}, {'type': 'done', 'sources': []}])
        response = stream_assistant(RequestFactory().get('/api/rag/stream/', {'query': 'Bonjour'}))
        self.assertEqual(response['X-Accel-Buffering'], 'no')
        self.assertIn('no-transform', response['Cache-Control'])
        stream = iter(response.streaming_content)
        self.assertIn(b'"type": "status"', next(stream))
        service.return_value.stream_query_events.assert_not_called()
        rest = b''.join(stream).decode()
        self.assertIn('Bonjour', rest)
        self.assertIn('"type": "done"', rest)

    @patch('apps.rag_engine.views.DRCRagService')
    def test_preparation_error_becomes_visible_stream_event(self, service):
        service.return_value.stream_query_events.side_effect = RuntimeError('retrieval failed')
        response = stream_assistant(RequestFactory().get('/api/rag/stream/', {'query': 'Actualités'}))
        events = [json.loads(part.decode()[6:]) for part in response.streaming_content]
        self.assertEqual(events[-1]['type'], 'error')
        self.assertNotIn('retrieval failed', events[-1]['message'])
