from unittest.mock import patch
from types import SimpleNamespace
import json

from django.core.cache import cache
from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from .models import OfficialNews
from .source_briefs import source_excerpt, snapshot_source_passages, select_resource_sections


class SourceBriefTests(SimpleTestCase):
    def test_long_document_selects_relevant_page_and_retains_page_url(self):
        sections = [{'title': f'Page {index}', 'text': 'Texte général. ' * 400,
                     'url': f'https://example.com/document.pdf#page={index}'} for index in range(1, 21)]
        sections[17]['text'] += ' Le permis est délivré après vérification.'
        selected = select_resource_sections(sections, 'Comment obtenir le permis ?')
        selected_page = next(page for page in selected if page['url'].endswith('#page=18'))
        self.assertIn('permis est délivré', selected_page['text'])
        self.assertLessEqual(sum(len(page['text']) for page in selected), 24000)
        self.assertTrue(any(page['partial'] for page in selected) or len(selected) < len(sections))

    def test_excerpt_comes_from_the_page_and_is_bounded(self):
        self.assertEqual(source_excerpt('<p>Premier fait</p> [suite](https://example.com)'), 'Premier fait suite')
        self.assertLessEqual(len(source_excerpt('A long passage. ' * 100)), 421)
        self.assertEqual(source_excerpt(None), '')

    def test_snapshot_does_not_assign_another_page_to_selected_url(self):
        snapshot = {'available': True, 'source_url':'https://example.com/one',
                    'text':'SOURCE: https://example.com/one\nTexte de la première page.\n\nSOURCE: https://example.com/two\nDeuxième page.',
                    'facts': {'fees': {'url':'https://example.com/two','text':'Frais exacts.'}}}
        passages = snapshot_source_passages(snapshot)
        self.assertIn('Texte de la première page', passages['https://example.com/one'])
        self.assertNotIn('Frais exacts', passages['https://example.com/one'])
        self.assertIn('Frais exacts', passages['https://example.com/two'])
        snapshot['available'] = False
        self.assertEqual(snapshot_source_passages(snapshot), {})


class SelectedArticleTests(TestCase):
    @patch('apps.rag_engine.views.ChromaSessionManager')
    @patch('apps.rag_engine.source_validation.validate_sources',
           side_effect=lambda question, sources, model, context='': sources)
    @patch('apps.rag_engine.mcp_tools.TavilyDRCSearchTool')
    @patch('apps.rag_engine.services.get_chat_ollama')
    @patch('apps.rag_engine.article_content.fetch_article_body')
    def test_selected_article_is_read_when_only_a_feed_excerpt_is_stored(self, fetch, model, search, reviewer, manager):
        article = OfficialNews.objects.create(title='Article sélectionné',slug='selected-resource-test',
            source_name='Actualité',source_url='https://example.com/selected',summary='Extrait RSS.',
            full_content='Extrait RSS.',published_at=timezone.now())
        cache.delete(f'article-body:{article.pk}')
        fetch.return_value = 'Contenu distinct du véritable article sélectionné.'
        model.return_value.stream.return_value = iter([SimpleNamespace(content='Voici les faits.')])
        search.return_value.search.return_value = {'structured': []}
        manager.return_value.get_session.return_value = None
        manager.return_value.save_message.return_value = True
        response = self.client.post(f'/api/rag/articles/{article.pk}/chat/',
            data=json.dumps({'query':'Que dit cet article ?'}),content_type='application/json')
        events = [json.loads(chunk.decode().removeprefix('data: ').strip()) for chunk in response.streaming_content]
        fetch.assert_called_once_with(article.source_url)
        self.assertIn(fetch.return_value, model.return_value.stream.call_args.args[0][1].content)
        selected = next(event['sources'][0] for event in events if event['type'] == 'sources')
        self.assertEqual(selected['excerpt'], fetch.return_value)
        self.assertEqual(selected['url'], article.source_url)
        article.refresh_from_db()
        self.assertEqual(article.full_content, fetch.return_value)
        cache.delete(f'article-body:{article.pk}')
