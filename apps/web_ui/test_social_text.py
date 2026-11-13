from unittest.mock import patch
from django.test import TestCase, override_settings
from apps.rag_engine.models import CommunityPost, CommunityComment
from apps.web_ui.social_accounts import account_from_url, search_batches
from apps.web_ui.social_sources import import_social_posts, repair_imported_posts
from apps.web_ui.social_text import extract_post


@override_settings(COMMUNITY_AUTO_BRIEFS=False, COMMUNITY_SOCIAL_DISCOVERY=False, TAVILY_API_KEY='test')
class SocialTextTests(TestCase):
    def setUp(self):
        photo_fetch = patch('apps.web_ui.social_images.fetch_x_photos',return_value=[])
        photo_fetch.start()
        self.addCleanup(photo_fetch.stop)

    def test_main_quote_is_separated_from_replies_counters_and_duplicate_text(self):
        message = ('#RDC : « Les sanctions ne suffiront pas à protéger les civils », HRW. '
                   'Selon @hrw_fr, il faut des mesures concrètes. HRW appelle à enquêter sur les exactions.')
        snippet = ('Title: Daniel Michombero /Batubenga on X: "#RDC : Les sanctions… / X\n'
                   '## Post. # Daniel Michombero /Batubenga on X: "' + message.replace('_', '\\_') + '". '
                   '#RDC : Les sanctions ne suffiront pas. 05:01:40 PM · 10/30/2026·9,468. '
                   '@michombero a REMINDER unrelated reply')
        result=extract_post('Daniel Michombero /Batubenga on X: "Titre tronqué', snippet)
        self.assertIsNotNone(result)
        self.assertIn('HRW appelle à enquêter',result['body'])
        self.assertIn('@hrw_fr',result['body'])
        for artifact in ('Title:', '## Post', 'REMINDER', '9,468', '\\_', 'on X:'):
            self.assertNotIn(artifact,result['body'])
            self.assertNotIn(artifact,result['title'])
        self.assertEqual(result['method'],'quoted_post')
        self.assertEqual(result['body'].count('Les sanctions'),1)

    def test_short_quoted_post_does_not_absorb_other_accounts(self):
        snippet=('Title: Auteur on X: "Les événements du lundi : le commandant était visé." / X\n'
                 '## Post. # Auteur on X: "Les événements du lundi : le commandant était visé.". '
                 'Autre personne : bilan non attribué. 02:19:17 PM · 10/30/2026·3,055. bro toujours présent')
        result=extract_post('Titre',snippet)
        self.assertEqual(result['body'],'Les événements du lundi : le commandant était visé.')

    def test_plain_excerpt_stops_before_timestamp(self):
        result=extract_post('RDC','Les services publics de Kinshasa changent leurs horaires. 05:01 PM · 10/30/2026 · reply')
        self.assertNotIn('reply',result['body'])
        self.assertIn('horaires',result['body'])

    def test_unclosed_quote_is_rejected_instead_of_guessing(self):
        self.assertIsNone(extract_post('Titre','## Post. # Someone on X: "Une très longue citation sans fin avec des réponses mélangées'))

    def test_compact_conversation_header_and_translation_prompt_are_removed(self):
        result=extract_post('Post','Conversation · @StanysBujakera · Stanis Bujakera Tshiamala · @StanysBujakera. Show translation. En RDC, le débat porte sur les services publics.Read more')
        self.assertEqual(result['body'],'En RDC, le débat porte sur les services publics.')

    @patch('apps.rag_engine.web_search.TavilyDRCSearchTool.results')
    def test_import_requires_exact_selected_account_and_retains_raw_excerpt(self, search):
        raw='## Post. # Radio Okapi on X: "Les services publics de Kinshasa changent leurs horaires.". reply'
        search.return_value=[{'url':'https://x.com/radiookapi/status/123','title':'Radio Okapi on X','snippet':raw},
            {'url':'https://x.com/fanaccount/status/999','title':'Radio Okapi en RDC','snippet':raw}]
        import_social_posts()
        post=CommunityPost.objects.get()
        self.assertEqual(post.author,'Radio Okapi')
        self.assertEqual(post.source_metadata['raw_excerpt'],raw)
        self.assertEqual(post.source_metadata['account'],'radiookapi')
        self.assertNotIn('reply',post.body)
        self.assertIsNone(account_from_url('https://x.com/fanaccount/status/999'))
        self.assertTrue(all(batch['domains']==['x.com','twitter.com'] for batch in search_batches()[:3]))
        self.assertEqual(search_batches()[-1]['domains'],['instagram.com'])

    def test_old_imports_are_repaired_without_losing_comments(self):
        post=CommunityPost.objects.create(kind='social',title='Daniel Michombero /Batubenga on X: "RDC',
            body='## Post. # Daniel Michombero /Batubenga on X: "Les services publics de Kinshasa changent leurs horaires.". reply',
            source_url='https://x.com/i/web/status/123',platform='X / Twitter',import_key='old')
        comment=CommunityComment.objects.create(post=post,author='Citoyen',body='Merci')
        result=repair_imported_posts();post.refresh_from_db()
        self.assertEqual(result['cleaned'],1)
        self.assertEqual(comment.post_id,post.pk)
        self.assertTrue(post.is_visible)
        self.assertNotIn('reply',post.body)
        original=dict(post.source_metadata)
        repair_imported_posts();post.refresh_from_db()
        self.assertEqual(post.source_metadata,original)

    def test_excluded_platforms_are_hidden_and_rejected_for_new_posts(self):
        for platform,url in [('Facebook','https://www.facebook.com/agency/posts/123'),('TikTok','https://www.tiktok.com/@agency/video/123')]:
            post=CommunityPost.objects.create(kind='social',title='RDC',body='Un message de Kinshasa',platform=platform,source_url=url,import_key=platform)
            self.assertEqual(self.client.post('/api/community/feed/',{'title':'test','body':'test','source_url':url},content_type='application/json').status_code,400)
            self.assertNotIn(post.pk,[item['id'] for item in self.client.get('/api/community/feed/?kind=social').json()['items']])
            self.assertEqual(self.client.get(f'/api/community/post/{post.pk}/comments/').status_code,404)
        repair_imported_posts()
        self.assertFalse(CommunityPost.objects.filter(is_visible=True).exists())
