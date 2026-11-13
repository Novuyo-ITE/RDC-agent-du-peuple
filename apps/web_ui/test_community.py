import json
from unittest.mock import patch
from django.core.cache import cache
from django.db import IntegrityError, OperationalError, transaction
from django.test import Client, TestCase, override_settings
from django.utils import timezone
from apps.rag_engine.models import OfficialNews, CommunityPost, CommunityComment, CommunityReaction
from apps.web_ui.community import generate_brief


@override_settings(COMMUNITY_AUTO_BRIEFS=False, COMMUNITY_SOCIAL_DISCOVERY=False)
class CommunityTests(TestCase):
    def setUp(self):
        cache.clear()
        article_fetch = patch('apps.rag_engine.article_content.fetch_article_body', return_value='')
        article_fetch.start()
        self.addCleanup(article_fetch.stop)
        self.article = OfficialNews.objects.create(title='Transport à Kinshasa', slug='transport-test',
            source_name='Radio Okapi', source_url='https://www.radiookapi.net/transport',
            summary='Un nouveau plan de transport est annoncé.', full_content='Le calendrier reste à préciser.',
            category='societe', published_at=timezone.now())
        self.other = OfficialNews.objects.create(title='Article masqué', slug='hidden-test',
            source_url='https://example.org/hidden', is_verified=False, published_at=timezone.now())
        self.post = CommunityPost.objects.create(title='Une question', body='Parlons transport.', author='Amina')

    def send(self, path, data, client=None):
        return (client or self.client).post(path, json.dumps(data), content_type='application/json')

    def url(self, action, item=None):
        return f'/api/community/news/{(item or self.article).pk}/{action}/'

    def test_page_and_feed_without_creating_posts(self):
        self.assertContains(self.client.get('/communaute/'), 'La communauté.')
        items = self.client.get('/api/community/feed/').json()['items']
        self.assertEqual({i['key'] for i in items}, {f'news:{self.article.pk}', f'post:{self.post.pk}'})
        self.assertEqual(CommunityPost.objects.count(), 1)

    def test_social_source_is_classified_and_persisted(self):
        response = self.send('/api/community/feed/', {'title':'Un lien', 'body':'Que pensez-vous de ceci ?',
            'author':'Patrick', 'source_url':'https://x.com/example/status/123'})
        self.assertEqual(response.status_code, 201)
        post = CommunityPost.objects.get(title='Un lien')
        self.assertEqual((post.kind, post.platform), ('social', 'X / Twitter'))
        items = self.client.get('/api/community/feed/?kind=social').json()['items']
        self.assertEqual([i['id'] for i in items], [post.pk])

    def test_spoofed_ai_and_platform_are_ignored(self):
        self.send('/api/community/feed/', {'title':'Fausse IA', 'body':'Opinion', 'kind':'ai', 'platform':'X / Twitter', 'author':'Assistant RDC'})
        self.assertEqual(CommunityPost.objects.get(title='Fausse IA').kind, 'community')

    def test_bad_links_and_payloads_are_rejected(self):
        for url in ('javascript:alert(1)', 'https://user:password@example.org/a'):
            self.assertEqual(self.send('/api/community/feed/', {'title':'test','body':'test','source_url':url}).status_code, 400)
        self.assertEqual(self.send('/api/community/feed/', []).status_code, 400)
        self.assertEqual(self.send('/api/community/feed/', {'title':'x'*241,'body':'test'}).status_code, 400)

    def test_likes_are_idempotent_and_per_visitor(self):
        for _ in range(2):
            self.assertEqual(self.send(self.url('like'), {'liked':True}).json()['likes'], 1)
        other_client=Client()
        self.assertEqual(self.send(self.url('like'), {'liked':True}, other_client).json()['likes'], 2)
        self.assertTrue(next(i for i in self.client.get('/api/community/feed/?kind=news').json()['items'] if i['target']=='news')['liked'])
        self.assertEqual(self.send(self.url('like'), {'liked':False}).json()['likes'], 1)

    def test_comments_survive_new_client_and_have_correct_counts(self):
        self.send(self.url('comments'), {'author':'Chantal', 'body':'Quels quartiers sont concernés ?'})
        self.send(self.url('like'), {'liked':True})
        self.send(self.url('like'), {'liked':True}, Client())
        thread=Client().get(self.url('comments')).json()
        self.assertEqual(thread['comments'][0]['author'], 'Chantal')
        item=next(i for i in self.client.get('/api/community/feed/?kind=news').json()['items'] if i['target']=='news')
        self.assertEqual((item['likes'],item['comments']),(2,1))

    def test_reply_cannot_cross_threads(self):
        parent=CommunityComment.objects.create(post=self.post,author='Amina',body='Question')
        self.assertEqual(self.send(self.url('comments'), {'body':'Réponse','parent':parent.pk}).status_code,404)

    def test_unverified_articles_and_hidden_posts_are_inaccessible(self):
        self.assertEqual(self.client.get(self.url('comments',self.other)).status_code,404)
        self.post.is_visible=False;self.post.save()
        self.assertEqual(self.client.get(f'/api/community/post/{self.post.pk}/comments/').status_code,404)

    def test_filters_and_pagination(self):
        self.assertEqual(len(self.client.get('/api/community/feed/?kind=news&category=societe').json()['items']),1)
        self.assertEqual(len(self.client.get('/api/community/feed/?kind=news&q=Kinshasa').json()['items']),1)
        self.assertEqual(self.client.get('/api/community/feed/?page=bad').status_code,400)
        self.assertEqual(self.client.get('/api/community/feed/?kind=bad').status_code,400)
        CommunityPost.objects.bulk_create([CommunityPost(title=f'Post {i}',body='Discussion') for i in range(20)])
        first=self.client.get('/api/community/feed/').json();second=self.client.get('/api/community/feed/?page=2').json()
        self.assertEqual(len(first['items']),15);self.assertTrue(first['has_more'])
        self.assertFalse({i['key'] for i in first['items']} & {i['key'] for i in second['items']})

    def test_default_feed_alternates_news_social_and_community(self):
        from datetime import timedelta
        self.article.published_at=timezone.now()-timedelta(days=1)
        self.article.save(update_fields=['published_at'])
        social=CommunityPost.objects.create(kind='social',title='Sur X',body='Publication partagée',
            platform='X / Twitter',source_url='https://x.com/example/status/1')
        brief=CommunityPost.objects.create(kind='ai',title='Décryptage',body='Résumé sourcé')
        items=self.client.get('/api/community/feed/').json()['items']
        self.assertEqual([i['key'] for i in items],
            [f'news:{self.article.pk}',f'post:{social.pk}',f'post:{brief.pk}',f'post:{self.post.pk}'])

    def test_mixed_feed_stays_diverse_across_pages_even_when_one_source_is_much_newer(self):
        from datetime import timedelta
        older=timezone.now()-timedelta(days=2)
        OfficialNews.objects.bulk_create([OfficialNews(title=f'Info {i}',slug=f'mixed-{i}',source_name='Radio Okapi',
            source_url='https://radiookapi.net/story',published_at=older) for i in range(30)])
        alternate=OfficialNews.objects.create(title='Autre média',slug='other-mixed',source_name='Actualite.cd',
            source_url='https://actualite.cd/story',published_at=older-timedelta(days=1))
        CommunityPost.objects.bulk_create([CommunityPost(kind='social',title=f'Social {i}',body='Sur X',
            author='Même compte',platform='X / Twitter') for i in range(30)])
        second_author=CommunityPost.objects.create(kind='social',title='Autre regard',body='Sur Instagram',author='Autre compte',platform='Instagram')
        first=self.client.get('/api/community/feed/').json()
        second=self.client.get('/api/community/feed/?page=2').json()
        self.assertEqual([i['target'] for i in first['items'][:4]],['news','post','news','post'])
        self.assertIn(f'news:{alternate.pk}',[i['key'] for i in first['items']])
        self.assertIn(f'post:{second_author.pk}',[i['key'] for i in first['items']])
        self.assertFalse({i['key'] for i in first['items']} & {i['key'] for i in second['items']})
        self.assertTrue(any(i['target']=='news' for i in second['items']))
        self.assertTrue(any(i['kind']=='social' for i in second['items']))

    def test_comment_history_pagination_and_hidden_comments(self):
        CommunityComment.objects.bulk_create([CommunityComment(article=self.article,author='Citoyen',body=str(i)) for i in range(55)])
        CommunityComment.objects.create(article=self.article,author='Spam',body='hidden',is_visible=False)
        first=self.client.get(self.url('comments')).json()
        self.assertEqual(len(first['comments']),50);self.assertTrue(first['has_more'])
        second=self.client.get(self.url('comments')+'?before='+str(first['before'])).json()
        self.assertEqual(len(second['comments']),5);self.assertFalse(second['has_more'])

    @patch('apps.web_ui.community.model_answer', return_value='Le calendrier n’est pas précisé. https://www.radiookapi.net/transport')
    def test_ai_response_is_marked_and_grounded_in_story_and_thread(self, model):
        response=self.send(self.url('ai'),{'author':'Amina','body':'Quand commence le plan ?'})
        self.assertEqual(response.status_code,201)
        reply=CommunityComment.objects.get(is_ai=True)
        self.assertIsNotNone(reply.parent_id)
        context=model.call_args.args[1]
        self.assertEqual(context['url'],self.article.source_url)
        self.assertIn('calendrier',context['text'])
        self.assertEqual(context['conversation'][-1]['body'],'Quand commence le plan ?')

    @patch('apps.web_ui.community.model_answer', side_effect=RuntimeError('offline'))
    def test_ai_failure_preserves_question(self, model):
        response=self.send(self.url('ai'),{'body':'Une explication ?'})
        self.assertEqual(response.status_code,503)
        self.assertEqual(CommunityComment.objects.filter(is_ai=False).count(),1)
        self.assertEqual(CommunityComment.objects.filter(is_ai=True).count(),0)

    @patch('apps.web_ui.community.model_answer', return_value='Bref résumé sourcé.')
    def test_briefs_are_source_linked_and_not_duplicated(self, model):
        post,created=generate_brief(self.article)
        again,repeated=generate_brief(self.article)
        self.assertTrue(created);self.assertFalse(repeated);self.assertEqual(post.pk,again.pk)
        self.assertEqual((post.kind,post.source_url),('ai',self.article.source_url))
        self.assertEqual(model.call_count,1)

    def test_csrf_is_required(self):
        client=Client(enforce_csrf_checks=True)
        self.assertEqual(self.send('/api/community/feed/',{'title':'Test','body':'Test'},client).status_code,403)
        client.get('/communaute/')
        response=client.post('/api/community/feed/',json.dumps({'title':'Test','body':'Test'}),content_type='application/json',HTTP_X_CSRFTOKEN=client.cookies['csrftoken'].value)
        self.assertEqual(response.status_code,201)

    def test_target_constraint(self):
        with self.assertRaises(IntegrityError),transaction.atomic():
            CommunityReaction.objects.create(visitor='nobody')

    def test_database_errors_distinguish_missing_migrations_from_full_disk(self):
        for detail, code in [('no such table: rag_engine_communitypost','migration_required'),
                             ('database or disk is full','storage_full'), ('database is locked','storage_busy')]:
            with patch('apps.web_ui.community.counts',side_effect=OperationalError(detail)):
                response=self.client.get('/api/community/feed/')
            self.assertEqual(response.status_code,503)
            self.assertEqual(response.json()['code'],code)

    @patch('apps.web_ui.community.model_answer',return_value='Réponse sourcée.')
    def test_ai_retry_reuses_existing_reply(self, model):
        parent=CommunityComment.objects.create(article=self.article,author='Citoyen',body='Expliquez.')
        first=self.send(self.url('ai'),{'body':parent.body,'parent':parent.pk})
        second=self.send(self.url('ai'),{'body':parent.body,'parent':parent.pk})
        self.assertEqual(first.json()['comment']['id'],second.json()['comment']['id'])
        self.assertEqual(model.call_count,1)

    @patch('apps.rag_engine.article_content.fetch_article_body',return_value='Texte intégral de la page : le calendrier sera annoncé vendredi.')
    @patch('apps.web_ui.community.model_answer',return_value='Selon Radio Okapi, le calendrier sera annoncé vendredi.\n\nLes habitants de Kinshasa sont concernés.')
    def test_news_summary_uses_page_text_and_keeps_original_photo_source_and_deep_link(self, model, fetch):
        self.article.image_url='https://www.radiookapi.net/original-photo.jpg'
        self.article.save()
        post,created=generate_brief(self.article)
        self.assertTrue(created)
        self.assertNotIn('\n',post.body)
        self.assertEqual(post.source_metadata['summary_basis'],'source_page')
        self.assertIn('Texte intégral',model.call_args.args[1]['article'])
        self.assertFalse(model.call_args.kwargs['include_citation'])
        items=self.client.get('/api/community/feed/').json()['items']
        story=next(item for item in items if item['target']=='news')
        self.assertEqual(story['image'],self.article.image_url)
        self.assertEqual(story['source_url'],self.article.source_url)
        self.assertEqual(story['article_url'],f'/actualites/?article={self.article.pk}')
        self.assertTrue(story['summary_ai'])
        self.assertEqual(story['body'],post.body)
        self.assertNotIn(f'post:{post.pk}',[item['key'] for item in items])
        ai=self.client.get('/api/community/feed/?kind=ai').json()['items'][0]
        self.assertEqual(ai['image'],self.article.image_url)
        self.assertEqual(ai['article_url'],story['article_url'])

    @patch('apps.web_ui.community.model_answer',return_value='Selon Radio Okapi, un plan de transport est annoncé.')
    def test_inaccessible_publication_uses_stored_text_with_visible_provenance(self, model):
        post,_=generate_brief(self.article)
        self.assertEqual(post.source_metadata['summary_basis'],'stored_text')
        item=self.client.get('/api/community/feed/?kind=news').json()['items'][0]
        self.assertEqual(item['summary_basis'],'stored_text')

    @patch('apps.rag_engine.article_content.fetch_article_body',return_value=('Faits du début. '*1000)+'Faits de la fin importants.')
    @patch('apps.web_ui.community.model_answer',return_value='Selon Radio Okapi, les faits sont résumés avec leurs réserves.')
    def test_long_article_is_read_in_full_before_final_summary(self, model, fetch):
        # Use enough text to exercise the multi-passage path rather than truncation.
        fetch.return_value=('Faits du début. '*2000)+'Faits de la fin importants.'
        post,_=generate_brief(self.article)
        self.assertGreater(post.source_metadata['chunks_read'],1)
        passages=[call.args[1].get('passage','') for call in model.call_args_list]
        self.assertIn('Faits de la fin importants.',''.join(passages))


@patch('apps.web_ui.news_refresh.refresh_news_if_due')
class NewsEditionTests(TestCase):
    def test_news_is_paginated_and_old_links_still_open(self, refresh):
        OfficialNews.objects.bulk_create([OfficialNews(title=f'Actualité {i}',slug=f'edition-{i}',
            source_name='Radio Okapi',source_url=f'https://example.org/{i}',published_at=timezone.now()) for i in range(25)])
        response=self.client.get('/actualites/')
        self.assertContains(response,'Le fil du Congo')
        self.assertEqual(len(response.context['news_list']),9)
        self.assertTrue(response.context['page_obj'].has_next())
        from bs4 import BeautifulSoup
        markup=BeautifulSoup(response.content,'html.parser')
        data=markup.select_one('[id^="news-data-"]')
        self.assertEqual(data['data-source'],'Radio Okapi')
        self.assertTrue(markup.select('.edition-brief-source [data-source-favicon]'))
        self.assertTrue(markup.select('.edition-timeline-footer [data-source-favicon]'))
        second=self.client.get('/actualites/?page=2')
        self.assertEqual(len(second.context['news_list']),9)
        article=OfficialNews.objects.order_by('pk').first()
        linked=self.client.get('/actualites/?article='+str(article.pk))
        self.assertEqual(linked.context['deep_link_article']['id'],str(article.pk))
