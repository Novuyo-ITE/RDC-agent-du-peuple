"""Best-effort original X photo discovery from its public embed metadata."""
import re
from urllib.parse import urlsplit, urljoin
import ipaddress

import requests
from django.core.cache import cache
from django.utils import timezone

from apps.rag_engine.models import CommunityPost

ARTICLE_HOSTS = ('radiookapi.net', 'actualite.cd', 'topcongo.live', 'rfi.fr', '7sur7.cd', 'politico.cd', 'deskeco.com')


def trusted_article_url(value):
    try:
        parsed=urlsplit(value)
        return parsed.scheme in ('http','https') and not parsed.username and not parsed.password and any(
            parsed.hostname == host or (parsed.hostname or '').endswith('.'+host) for host in ARTICLE_HOSTS)
    except (ValueError,TypeError):
        return False


def public_image_url(value):
    try:
        parsed=urlsplit(value)
        if parsed.scheme not in ('http','https') or not parsed.hostname or parsed.username or parsed.password:
            return False
        if parsed.hostname in ('localhost',) or parsed.hostname.endswith(('.local','.internal')):
            return False
        try:
            if not ipaddress.ip_address(parsed.hostname).is_global:
                return False
        except ValueError:
            pass
        return not re.search(r'(?:logo|avatar|profile_image|favicon|tracking|pixel|\.svg(?:\?|$))',value,re.I)
    except (ValueError,TypeError):
        return False


def body_media(data):
    """Search only the original post's own rich body, not surrounding discussions."""
    found=[]
    def visit(node,depth=0):
        if depth>8:
            return
        if isinstance(node,list):
            for child in node:
                visit(child,depth+1)
        elif isinstance(node,dict):
            for key,value in node.items():
                if key in ('quoted_tweet','quoted_status','retweeted_status','replies','related','user','author'):
                    continue
                if key in ('url','src','media_url','media_url_https','original_img_url') and valid_x_photo(value):
                    found.append(value)
                elif isinstance(value,(dict,list)):
                    visit(value,depth+1)
    for key in ('entities','extended_entities','note_tweet','article'):
        visit(data.get(key))
    return list(dict.fromkeys(found))[:4]


def full_post_text(data):
    """Use only this author's native text, preferring long-form text over previews."""
    note=data.get('note_tweet') or {}
    candidates=[]
    if isinstance(note,dict):
        results=note.get('note_tweet_results') or {}
        result=results.get('result') or {} if isinstance(results,dict) else {}
        if isinstance(result,dict):
            candidates.append(result.get('text'))
        candidates.append(note.get('text'))
    results=data.get('note_tweet_results') or {}
    result=results.get('result') or {} if isinstance(results,dict) else {}
    if isinstance(result,dict):
        candidates.append(result.get('text'))
    for value in candidates:
        if isinstance(value,str) and value.strip():
            return value.strip()
    if data.get('truncated'):
        return ''
    text=data.get('text')
    return text.strip() if isinstance(text,str) else ''


def article_body_photos(article_url):
    """Read inline/lazy-loaded pictures inside the linked publisher's main article."""
    if not trusted_article_url(article_url):
        return []
    from bs4 import BeautifulSoup
    try:
        url=article_url
        for _ in range(4):
            response=requests.get(url,timeout=(3,8),allow_redirects=False,headers={'User-Agent':'Mozilla/5.0 (compatible; DRCNewsReader/1.0)'})
            if response.status_code in (301,302,303,307,308):
                url=urljoin(url,response.headers.get('Location',''))
                if not trusted_article_url(url):
                    return []
                continue
            response.raise_for_status()
            break
        else:
            return []
        soup=BeautifulSoup(response.text,'html.parser')
        for node in soup.select('nav,header,footer,aside,.related-posts,.related,.social-share,.comments'):
            node.decompose()
        root=None
        for selector in ('[itemprop="articleBody"]','.field--name-body','.field-name-body','.entry-content','.article-content','article','main'):
            root=soup.select_one(selector)
            if root:
                break
        if not root:
            return []
        photos=[]
        for image in root.select('img'):
            dimensions=[int(image.get(key)) for key in ('width','height') if str(image.get(key,'')).isdigit()]
            if dimensions and max(dimensions)<120:
                continue
            value=image.get('data-src') or image.get('data-original') or image.get('data-lazy-src')
            srcset=image.get('data-srcset') or image.get('srcset')
            if not value and srcset:
                value=srcset.split(',')[-1].strip().split()[0]
            value=value or image.get('src','')
            candidate=urljoin(url,value)
            if value and public_image_url(candidate):
                photos.append(candidate)
        return list(dict.fromkeys(photos))[:4]
    except (requests.RequestException,ValueError,TypeError):
        return []


def linked_article_media(data):
    entities=data.get('entities') or {}
    links=(entities.get('urls') or []) if isinstance(entities,dict) else []
    for link in links if isinstance(links,list) else []:
        if not isinstance(link,dict):
            continue
        url=link.get('expanded_url') or link.get('unwound_url')
        if trusted_article_url(url):
            photos=article_body_photos(url)
            if photos:
                return photos,url
    return [],''


def valid_social_photo(value, metadata):
    return valid_x_photo(value) or (metadata.get('image_source')=='linked_article' and
        trusted_article_url(metadata.get('image_article_url')) and public_image_url(value))


def valid_x_photo(value):
    if not isinstance(value, str) or len(value) > 2000:
        return False
    try:
        url = urlsplit(value)
        return (url.scheme == 'https' and url.hostname == 'pbs.twimg.com' and
                not url.username and not url.password and url.path.startswith(('/media/', '/card_img/')))
    except ValueError:
        return False


def fetch_x_photos(post_url, expected_account='', force=False):
    """Require a matching tweet ID and author; never inspect replies or quoted posts."""
    try:
        parsed = urlsplit(post_url)
        if parsed.scheme != 'https' or parsed.hostname not in ('x.com', 'twitter.com', 'www.x.com', 'www.twitter.com'):
            return []
        match = re.fullmatch(r'/(?:[^/]+|i/web)/status/(\d+)/?', parsed.path)
        if not match:
            return []
        tweet_id = match.group(1)
        key = f'community-x-photos:{tweet_id}:{expected_account.lower()}'
        saved = cache.get(key)
        if saved is not None and not force:
            return saved
        response = requests.get('https://cdn.syndication.twimg.com/tweet-result',
            params={'id': tweet_id, 'lang': 'fr', 'token': 'true'},
            headers={'User-Agent': 'Mozilla/5.0 (compatible; DRCNewsReader/1.0)'},
            timeout=(3, 8), allow_redirects=False)
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, dict) or str(data.get('id_str', '')) != tweet_id:
            return []
        account = (data.get('user') or {}).get('screen_name', '')
        if expected_account and account.casefold() != expected_account.casefold():
            return []
        cache.set(f'community-x-body:{tweet_id}:{expected_account.lower()}',data,3600)
        candidates = [photo.get('url') for photo in data.get('photos', []) if isinstance(photo, dict)]
        candidates += [photo.get('media_url_https') for photo in data.get('mediaDetails', [])
                       if isinstance(photo, dict) and photo.get('type') == 'photo']
        photos = list(dict.fromkeys(url for url in candidates if valid_x_photo(url)))[:4]
        if not photos:
            photos=body_media(data)
        if not photos:
            # Older posts often share an article preview instead of an attached
            # photo. Read only this post's own card, never the quoted post's card.
            card = data.get('card') or {}
            bindings = card.get('binding_values', {}) if isinstance(card, dict) else {}
            if isinstance(bindings, list):
                bindings = {entry.get('key'): entry.get('value', {}) for entry in bindings if isinstance(entry, dict)}
            if isinstance(bindings, dict):
                for name in ('thumbnail_image_original', 'thumbnail_image_large', 'summary_photo_image_large',
                             'photo_image_full_size_original', 'thumbnail_image', 'summary_photo_image'):
                    entry = bindings.get(name) or {}
                    image = entry.get('image_value') or {} if isinstance(entry, dict) else {}
                    value = image.get('url') if isinstance(image, dict) else None
                    if valid_x_photo(value):
                        photos = [value]
                        break
        cache.set(key, photos, 21600 if photos else 3600)
        return photos
    except (requests.RequestException, ValueError, TypeError, AttributeError):
        if 'key' in locals():
            cache.set(key, [], 900)
        return []


def enrich_post_images(post, force=False):
    if post.kind != 'social' or post.platform != 'X / Twitter' or not post.is_visible:
        return False
    metadata = dict(post.source_metadata or {})
    photos = fetch_x_photos(post.source_url, metadata.get('account', ''), force=force)
    source='x_embed'
    article_url=''
    tweet_id=post.source_url.rstrip('/').split('/')[-1]
    data=cache.get(f'community-x-body:{tweet_id}:{metadata.get("account", "").lower()}')
    native_text=full_post_text(data) if isinstance(data,dict) else ''
    if native_text:
        metadata.update(text_source='x_embed',text_complete=True,full_text_checked_at=timezone.now().isoformat())
        post.body=native_text
        CommunityPost.objects.filter(pk=post.pk).update(body=native_text,source_metadata=metadata)
        post.source_metadata=metadata
    if not photos:
        if isinstance(data,dict):
            photos,article_url=linked_article_media(data)
            source='linked_article'
    # A temporary failure must not remove previously discovered photos.
    if not photos:
        return False
    metadata.update(images=photos, image_source=source, image_checked_at=timezone.now().isoformat())
    if article_url:
        metadata['image_article_url']=article_url
    CommunityPost.objects.filter(pk=post.pk).update(source_metadata=metadata)
    post.source_metadata = metadata
    return True


def backfill_social_images(limit=30, force=False, include_text=False):
    from django.db.models import Q
    missing=Q(source_metadata__images__isnull=True) | Q(source_metadata__images=[])
    if include_text:
        missing |= Q(source_metadata__text_complete__isnull=True) | Q(source_metadata__text_complete=False)
    posts = CommunityPost.objects.filter(kind='social', platform='X / Twitter', is_visible=True).filter(missing).order_by('created_at', 'pk')[:limit]
    return sum(enrich_post_images(post, force=force) for post in posts)
