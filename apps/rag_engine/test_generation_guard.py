from types import SimpleNamespace
from unittest.mock import patch
from django.test import SimpleTestCase
from .generation_guard import bounded_chunks


class GenerationGuardTests(SimpleTestCase):
    def stream(self, pieces, closed):
        try:
            for text in pieces:
                yield SimpleNamespace(content=text)
        finally:
            closed.append(True)

    def test_normal_answer_is_preserved_and_stream_closed(self):
        closed = []
        result = list(bounded_chunks(self.stream(['## Hatua\n', '1. Andaa hati.\n', '2. Wasiliana na ofisi.'], closed)))
        self.assertEqual(len(result), 3)
        self.assertEqual(closed, [True])

    def test_repeated_lingala_and_swahili_stop_across_chunk_boundaries(self):
        for phrase in ['Esengeli kokende na biro mpo na kozwa mikanda. ',
                       'Unahitaji kwenda ofisini kupata taarifa sahihi. ']:
            closed = []
            text = phrase * 100
            pieces = [text[i:i+7] for i in range(0, len(text), 7)]
            result = ''.join(chunk.content for chunk in bounded_chunks(self.stream(pieces, closed)))
            self.assertLess(len(result), len(phrase) * 4)
            self.assertEqual(closed, [True])

    def test_output_budget_closes_upstream(self):
        closed = []
        result = list(bounded_chunks(self.stream(['12345', '67890', 'extra'], closed), max_chars=10))
        self.assertEqual(len(result), 2)
        self.assertEqual(closed, [True])

    @patch('apps.rag_engine.generation_guard.time.monotonic', side_effect=[0, 1, 121])
    def test_time_budget(self, clock):
        closed = []
        result = list(bounded_chunks(self.stream(['start', 'late'], closed)))
        self.assertEqual(len(result), 1)
        self.assertEqual(closed, [True])
