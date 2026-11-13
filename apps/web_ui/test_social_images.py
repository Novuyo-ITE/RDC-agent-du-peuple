from unittest.mock import Mock, patch
import requests
from django.core.cache import cache
from django.test import TestCase, override_settings
from apps.rag_engine.models import CommunityPost
from apps.web_ui.social_images import fetch_x_photos, enrich_post_images, backfill_social_images, article_body_photos, full_post_text
from apps.web_ui.social_accounts import instagram_attribution
from apps.web_ui.social_sources import import_social_posts


@override_settings(COMMUNITY_AUTO_BRIEFS=False,COMMUNITY_SOCIAL_DISCOVERY=False,TAVILY_API_KEY='test')
class SocialImageTests(TestCase):
    def setUp(self):
        cache.clear()

    @patch('apps.web_ui.social_images.requests.get')
    def test_photos_belong_to_original_post_not_avatar_quote_or_reply(self, get):
        get.return_value.json.return_value={'id_str':'123','user':{'screen_name':'radiookapi','profile_image_url':'https://pbs.twimg.com/profile_images/avatar.jpg'},
            'photos':[{'url':'https://pbs.twimg.com/media/photo.jpg'},{'url':'https://evil.example/image.jpg'},
                      {'url':'https://pbs.twimg.com/profile_images/avatar.jpg'}],
            'quoted_tweet':{'photos':[{'url':'https://pbs.twimg.com/media/quoted.jpg'}]},
            'mediaDetails':[{'type':'photo','media_url_https':'https://pbs.twimg.com/media/photo.jpg'}]}
        photos=fetch_x_photos('https://x.com/i/web/status/123','radiookapi')
        self.assertEqual(photos,['https://pbs.twimg.com/media/photo.jpg'])
        self.assertEqual(get.call_args.kwargs['params']['id'],'123')
        fetch_x_photos('https://x.com/i/web/status/123','radiookapi')
        self.assertEqual(get.call_count,1)

    @patch('apps.web_ui.social_images.requests.get')
    def test_wrong_post_or_account_is_rejected(self,get):
        for data in [{'id_str':'999','user':{'screen_name':'radiookapi'}},
                     {'id_str':'123','user':{'screen_name':'someoneelse'}}]:
            get.return_value.json.return_value={**data,'photos':[{'url':'https://pbs.twimg.com/media/a.jpg'}]}
            self.assertEqual(fetch_x_photos('https://x.com/i/web/status/123','radiookapi'),[])

    @patch('apps.web_ui.social_images.requests.get',side_effect=requests.Timeout())
    def test_network_failure_keeps_post_and_previous_photo(self,get):
        post=CommunityPost.objects.create(kind='social',title='RDC',body='A post',platform='X / Twitter',
            source_url='https://x.com/i/web/status/123',source_metadata={'account':'radiookapi','images':['https://pbs.twimg.com/media/old.jpg']})
        self.assertFalse(enrich_post_images(post))
        post.refresh_from_db()
        self.assertEqual(post.source_metadata['images'],['https://pbs.twimg.com/media/old.jpg'])

    def test_feed_exposes_photo_and_rejects_avatar_urls(self):
        post=CommunityPost.objects.create(kind='social',title='RDC',body='A post',platform='X / Twitter',
            source_url='https://x.com/i/web/status/123',source_metadata={'images':[
                'https://pbs.twimg.com/profile_images/avatar.jpg','https://pbs.twimg.com/media/photo.jpg']})
        item=self.client.get('/api/community/feed/?kind=social').json()['items'][0]
        self.assertEqual(item['image'],'https://pbs.twimg.com/media/photo.jpg')
        self.assertEqual(item['images'],['https://pbs.twimg.com/media/photo.jpg'])

    @patch('apps.web_ui.social_images.requests.get')
    def test_picture_inside_long_post_body_is_recovered_without_quote_media(self,get):
        get.return_value.json.return_value={'id_str':'123','user':{'screen_name':'radiookapi'},
            'article':{'content':{'blocks':[{'text':'Introduction'},{'media':{'original_img_url':'https://pbs.twimg.com/media/inline.jpg'}}],
                'quoted_tweet':{'url':'https://pbs.twimg.com/media/unrelated.jpg'}}}}
        self.assertEqual(fetch_x_photos('https://x.com/i/web/status/123','radiookapi'),['https://pbs.twimg.com/media/inline.jpg'])

    @patch('apps.web_ui.social_images.requests.get')
    def test_article_body_lazy_image_is_found_after_intro_and_sidebars_are_ignored(self,get):
        get.return_value.status_code=200
        get.return_value.text='''<main><img src="/logo.png"><article><p>Long introduction</p><div class="entry-content"><p>Another paragraph</p><figure><img data-src="/uploads/body-photo.jpg" width="800" height="500"></figure><aside><img src="/unrelated.jpg"></aside></div></article></main>'''
        self.assertEqual(article_body_photos('https://actualite.cd/a-story'),['https://actualite.cd/uploads/body-photo.jpg'])
        get.assert_called_once()
        get.return_value.status_code=302
        get.return_value.headers={'Location':'http://127.0.0.1/private'}
        self.assertEqual(article_body_photos('https://actualite.cd/a-story'),[])

    @patch('apps.web_ui.social_images.fetch_x_photos',return_value=[])
    @patch('apps.web_ui.social_images.article_body_photos',return_value=['https://actualite.cd/uploads/body-photo.jpg'])
    def test_linked_article_picture_keeps_provenance_and_is_returned_by_feed(self,read,fetch):
        cache.set('community-x-body:123:radiookapi',{'text':'Original post text',
            'entities':{'urls':[{'expanded_url':'https://actualite.cd/a-story'}]}},3600)
        post=CommunityPost.objects.create(kind='social',title='RDC',body='A post',platform='X / Twitter',
            source_url='https://x.com/i/web/status/123',source_metadata={'account':'radiookapi'})
        self.assertTrue(enrich_post_images(post))
        item=self.client.get('/api/community/feed/?kind=social').json()['items'][0]
        self.assertEqual(item['image'],'https://actualite.cd/uploads/body-photo.jpg')
        self.assertEqual(item['image_article_url'],'https://actualite.cd/a-story')

    @patch('apps.web_ui.social_images.requests.get')
    def test_full_long_post_text_is_saved_and_returned_without_truncation(self,get):
        text=('Un long passage du post.\n'*300)+'Dernière phrase du post.'
        get.return_value.json.return_value={'id_str':'123','user':{'screen_name':'radiookapi'},
            'text':'A truncated preview…','truncated':True,
            'note_tweet':{'note_tweet_results':{'result':{'text':text}}},
            'quoted_tweet':{'text':'Someone else reply'}}
        post=CommunityPost.objects.create(kind='social',title='RDC',body='An old excerpt',platform='X / Twitter',
            source_url='https://x.com/i/web/status/123',source_metadata={'account':'radiookapi'})
        enrich_post_images(post,force=True)
        post.refresh_from_db()
        self.assertEqual(post.body,text)
        self.assertTrue(post.source_metadata['text_complete'])
        item=self.client.get('/api/community/feed/?kind=social').json()['items'][0]
        self.assertEqual(item['body'],text)
        self.assertTrue(item['text_complete'])
        self.assertEqual(full_post_text({'text':'Truncated…','truncated':True}),'')

    @patch('apps.web_ui.social_images.requests.get')
    def test_older_link_post_can_use_its_own_card_picture(self,get):
        cache.set('community-x-photos:123:radiookapi',[],3600)
        get.return_value.json.return_value={'id_str':'123','user':{'screen_name':'radiookapi'},'card':{
            'binding_values':{'thumbnail_image_large':{'image_value':{'url':'https://pbs.twimg.com/card_img/123/image.jpg'}}}},
            'quoted_tweet':{'photos':[{'url':'https://pbs.twimg.com/media/quoted.jpg'}]}}
        self.assertEqual(fetch_x_photos('https://x.com/i/web/status/123','radiookapi',force=True),['https://pbs.twimg.com/card_img/123/image.jpg'])
        self.assertEqual(get.call_count,1)

    @patch('apps.web_ui.social_images.enrich_post_images',return_value=True)
    def test_backfill_prioritizes_old_missing_images_and_skips_already_illustrated_posts(self,enrich):
        old=CommunityPost.objects.create(kind='social',title='Old',body='Old post',platform='X / Twitter')
        CommunityPost.objects.create(kind='social',title='Has image',body='Has image',platform='X / Twitter',
            source_metadata={'images':['https://pbs.twimg.com/media/photo.jpg']})
        CommunityPost.objects.create(kind='social',title='New',body='New post',platform='X / Twitter')
        self.assertEqual(backfill_social_images(limit=1,force=True),1)
        self.assertEqual(enrich.call_args.args[0].pk,old.pk)
        self.assertTrue(enrich.call_args.kwargs['force'])

    @patch('apps.rag_engine.web_search.TavilyDRCSearchTool.results')
    def test_instagram_import_requires_publisher_attribution_not_just_mentions(self,search):
        caption='RDC : les services publics de Kinshasa changent leurs horaires.'
        good={'url':'https://www.instagram.com/p/Abc123','title':'RDC à Kinshasa',
              'snippet':'12 likes, 0 comments - actualite.cd on November 6, 2026: "'+caption+'"'}
        bad={'url':'https://www.instagram.com/p/Wrong123','title':'ACTUALITE.CD en RDC',
             'snippet':'Une publication sur la RDC mentionne @actualite.cd sans en être l’auteur.'}
        search.return_value=[good,bad]
        self.assertEqual(instagram_attribution(good),'actualite.cd')
        self.assertIsNone(instagram_attribution(bad))
        import_social_posts()
        post=CommunityPost.objects.get()
        self.assertEqual(post.platform,'Instagram')
        self.assertEqual(post.author,'ACTUALITE.CD')
        self.assertEqual(post.body,caption)
        self.assertEqual(post.source_metadata['account_platform'],'instagram')
