from django.test import SimpleTestCase
from types import SimpleNamespace
from .citations import cited_sources, validate_citation_paragraphs, citation_chunks, numbered_citation_chunks, answer_references


class CitationTests(SimpleTestCase):
    def test_numbered_sources_become_exact_links_even_across_stream_chunks(self):
        sources = [{'url': 'https://example.cd/one'}, {'url': 'https://example.cd/two'}]
        chunks = (SimpleNamespace(content=value) for value in ['Bonjour ', '[SOU', 'RCE ', '2]', '. Fin.'])
        output = numbered_citation_chunks(chunks, sources)
        self.assertEqual(next(output).content, 'Bonjour ')
        self.assertEqual(''.join(chunk.content for chunk in output), '[Source 2](https://example.cd/two). Fin.')

    def test_numbered_source_does_not_invent_urls_or_break_existing_links(self):
        sources = [{'url': 'https://example.cd/one'}]
        chunks = [SimpleNamespace(content='[SOURCE 9] puis [SOURCE 1](https://example.cd/one)')]
        answer = ''.join(chunk.content for chunk in numbered_citation_chunks(chunks, sources))
        self.assertEqual(answer, '[Source non disponible] puis [SOURCE 1](https://example.cd/one)')

    def test_parenthesized_sources_from_stream_become_exact_links(self):
        sources = [{'url': 'https://example.cd/one'}, {'url': 'https://example.cd/two'}]
        chunks = (SimpleNamespace(content=value) for value in [
            'Les routes sont dégradées (SO', 'URCE ', '1). Puis (source 2', ').',
        ])
        answer = ''.join(chunk.content for chunk in numbered_citation_chunks(chunks, sources))
        self.assertEqual(answer, 'Les routes sont dégradées ([Source 1](https://example.cd/one)). Puis ([Source 2](https://example.cd/two)).')
        self.assertEqual(cited_sources(answer, sources), sources)

    def test_parenthesized_missing_source_and_normal_parentheses(self):
        sources = [{'url': 'https://example.cd/one'}]
        chunks = (SimpleNamespace(content=value) for value in ['Texte (', 'une précision', ') (SOURCE 9)'])
        output = numbered_citation_chunks(chunks, sources)
        self.assertEqual(next(output).content, 'Texte ')
        self.assertEqual(next(output).content, '(')
        self.assertEqual(''.join(chunk.content for chunk in output), 'une précision) ([Source non disponible])')

    def test_uncited_photo_is_preserved_after_text_only_news(self):
        sources = [
            {'url':f'https://example.cd/text-{index}','source_kind':'news'} for index in range(4)
        ] + [{'url':'https://example.cd/photo-story','image_url':'https://example.cd/photo.jpg','source_kind':'news'}]
        refs = answer_references('Une réponse sans liens.', sources)
        self.assertIn('https://example.cd/photo-story', [source['url'] for source in refs])

    def test_uncited_article_and_photo_remain_available_as_retrieved_reference(self):
        article = {'url':'https://example.cd/article','image_url':'https://example.cd/photo.jpg','source_kind':'news'}
        portal = {'url':'https://mines.gouv.cd','source_kind':'directory'}
        refs = answer_references('Une réponse sans liens.', [article,portal])
        self.assertEqual(len(refs),1)
        self.assertTrue(refs[0]['reference_only'])
        self.assertEqual(refs[0]['image_url'], article['image_url'])
        self.assertNotIn('reference_only', article)

    def test_text_streams_before_model_finishes_a_paragraph(self):
        consumed = []
        def model():
            for text in ['Voici ', 'la réponse ', 'progressive.']:
                consumed.append(text)
                yield SimpleNamespace(content=text)
        output = citation_chunks(model(), [])
        self.assertEqual(next(output).content, 'Voici ')
        self.assertEqual(consumed, ['Voici '])
        self.assertEqual(next(output).content, 'la réponse ')
        self.assertEqual(consumed, ['Voici ', 'la réponse '])
        output.close()

    def test_invented_article_paragraph_removed_not_replaced_with_homepage(self):
        sources = [{'url': 'https://mines.gouv.cd/'}]
        answer = 'Une nouvelle loi : [voir](https://mines.gouv.cd/nouvelle-loi).\n\nDétail non confirmé.'
        checked = validate_citation_paragraphs(answer, sources)
        self.assertNotIn('nouvelle loi', checked)
        self.assertIn('Détail non confirmé.', checked)

    def test_stream_checks_urls_split_across_tokens(self):
        pieces = ['Une annonce [ici](https://mines.', 'gouv.cd/invente).\n', '\nConsultez [la page](https://mines.gouv.cd/article).']
        chunks = (SimpleNamespace(content=piece) for piece in pieces)
        output = ''.join(chunk.content for chunk in citation_chunks(chunks, [{'url': 'https://mines.gouv.cd/article'}]))
        self.assertNotIn('invente', output)
        self.assertIn('https://mines.gouv.cd/article', output)

    def test_only_exact_cited_pages_and_no_duplicates(self):
        sources = [{'url': 'https://example.cd/'}, {'url': 'https://example.cd/news'},
                   {'url': 'https://other.cd/'}, {'url': 'https://example.cd/news'}]
        self.assertEqual(cited_sources('[Article](https://example.cd/news).', sources), [sources[1]])

    def test_missing_citation_does_not_promote_retrieved_pages(self):
        self.assertEqual(cited_sources('Information indisponible.', [{'url': 'https://example.cd'}]), [])

    def test_fragment_and_trailing_slash_match_but_query_is_preserved(self):
        sources = [{'url': 'https://example.cd/info/'}, {'url': 'https://example.cd/info?q=other'}]
        self.assertEqual(cited_sources('https://example.cd/info#section', sources), [sources[0]])
