"""Discover indexed public social posts with Tavily; never simulate a social API feed."""
import hashlib
import logging
import re
import threading
from urllib.parse import parse_qs, urlencode, urlsplit, urlunsplit

from django.conf import settings
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.db import close_old_connections
from django.utils import timezone

from apps.rag_engine.models import CommunityPost
from apps.rag_engine.web_search import TavilyDRCSearchTool, TavilySearchError
from .social_accounts import SOCIAL_ACCOUNTS, INSTAGRAM_ACCOUNTS, account_from_url, instagram_attribution, search_batches
from .social_text import extract_post

logger = logging.getLogger(__name__)
STATUS_KEY = 'community-social-status'
EXCLUDED_PLATFORMS = ('Facebook', 'TikTok')
EXCLUDED_URL_PATTERN = r'^https?://([^/]+\.)?(facebook\.com|fb\.com|fb\.watch|tiktok\.com)([/:?#]|$)'


def platform_excluded(url):
    return bool(re.search(EXCLUDED_URL_PATTERN, url or '', re.I))


def canonical_post_url(value):
    """Only accept social publication URLs, not profiles, search pages or login walls."""
    from apps.web_ui.community import source_platform, PLATFORMS
    if not isinstance(value, str) or len(value) > 1024:
        return None
    if platform_excluded(value):
        return None
    try:
        platform = source_platform(value)
        if platform not in PLATFORMS.values():
            return None
        parsed = urlsplit(value)
        host = parsed.hostname.lower().removeprefix('www.').removeprefix('m.').removeprefix('mobile.')
        path = parsed.path.rstrip('/')
        query = parse_qs(parsed.query)
        keep = {}
        if host in ('x.com', 'twitter.com'):
            match = re.fullmatch(r'/(?:[^/]+|i/web)/status/(\d+)(?:/(?:photo|video)/\d+)?', path)
            if not match:
                return None
            # A stable publication identity also deduplicates renamed X handles.
            host, path = 'x.com', '/i/web/status/' + match.group(1)
        elif host == 'youtu.be':
            if not re.fullmatch(r'/[A-Za-z0-9_-]{6,}', path):
                return None
            host, keep, path = 'youtube.com', {'v': path[1:]}, '/watch'
        elif host == 'youtube.com':
            if path == '/watch' and query.get('v'):
                keep = {'v': query['v'][0]}
            elif re.fullmatch(r'/(?:shorts|live)/[A-Za-z0-9_-]+', path):
                keep, path = {'v': path.rsplit('/', 1)[-1]}, '/watch'
            else:
                return None
        elif host == 'facebook.com':
            if path in ('/story.php', '/permalink.php') and query.get('story_fbid') and query.get('id'):
                keep = {key: query[key][0] for key in ('id', 'story_fbid')}
            elif path in ('/watch', '/video.php') and query.get('v'):
                keep = {'v': query['v'][0]}
            elif not re.search(r'/(?:posts|videos|reel)/[^/]+|/share/(?:p|v|r)/[^/]+', path):
                return None
        elif host == 'instagram.com':
            if not re.fullmatch(r'/(?:p|reel|tv)/[^/]+', path):
                return None
        elif host == 'tiktok.com':
            if not re.fullmatch(r'/@[^/]+/video/\d+', path):
                return None
        elif host == 'linkedin.com':
            if not (path.startswith('/posts/') or path.startswith('/feed/update/')):
                return None
        elif host == 'bsky.app':
            if not re.fullmatch(r'/profile/[^/]+/post/[^/]+', path):
                return None
        elif host in ('threads.net', 'threads.com'):
            if not re.fullmatch(r'/@[^/]+/post/[^/]+', path):
                return None
            host = 'threads.com'
        else:
            return None
        return urlunsplit(('https', host, path, urlencode(keep), '')), platform
    except (ValueError, ValidationError):
        return None


def import_social_posts():
    """Six bounded searches covering media, voices, institutions, figures and embassies."""
    if not getattr(settings, 'TAVILY_API_KEY', ''):
        raise TavilySearchError('Clé Tavily non configurée sur le serveur.')
    searcher = TavilyDRCSearchTool(max_results=5)
    created = 0
    failed = 0
    found = 0
    offset = cache.get('community-account-cursor', 0)
    batches = search_batches(offset)
    for batch in batches:
        try:
            records = searcher.results(batch['query'], include_domains=batch['domains'], time_range='week')
        except TavilySearchError:
            failed += 1
            logger.warning('Social discovery unavailable for a Tavily domain group.')
            continue
        for record in records:
            if not isinstance(record, dict):
                continue
            canonical = canonical_post_url(record.get('url'))
            instagram = instagram_attribution(record)
            account = account_from_url(record.get('url')) or instagram
            title, snippet = record.get('title', ''), record.get('snippet', '')
            if not canonical or not account or not isinstance(title, str) or not isinstance(snippet, str):
                continue
            # Some search hits mention Congo-Brazzaville or unrelated countries.
            if not re.search(r'\b(?:RDC|DRC|Kinshasa|Goma|Kivu|Lubumbashi|Tshisekedi)\b|Congo.{0,20}d[ée]mocratique|d[ée]mocratique.{0,20}Congo',
                             title + ' ' + snippet, re.IGNORECASE):
                continue
            if not title.strip() or not snippet.strip():
                continue
            caption = snippet
            if instagram:
                # Strip the platform's explicit publisher/date metadata, retaining
                # only the caption, never comments or automatically described images.
                caption = re.sub(r'^\s*[\d.,KMk]+\s+likes?,\s*[\d.,KMk]+\s+comments?\s*[-–].*?:\s*["“]?', '', caption, count=1, flags=re.I)
                caption = re.sub(r'^\s*(?:Photo|Video|Reel|Post) by .*? on [^.\n]+\.\s*', '', caption, count=1, flags=re.I)
                caption = re.split(r'\bMay be an image\b|\bSee more posts\b|\n\s*(?:Photo|Video) by ', caption, maxsplit=1, flags=re.I)[0].strip().rstrip('"”')
            cleaned = extract_post(title, caption)
            if not cleaned:
                continue
            url, platform = canonical
            fingerprint = hashlib.sha256(url.encode()).hexdigest()
            found += 1
            # Do not resurrect hidden posts or overwrite human-authored posts.
            existing = CommunityPost.objects.filter(source_url=url).first()
            if existing:
                if existing.import_key and existing.is_visible and (not (existing.source_metadata or {}).get('images') or not (existing.source_metadata or {}).get('text_complete')):
                    from .social_images import enrich_post_images
                    enrich_post_images(existing)
                continue
            post, added = CommunityPost.objects.get_or_create(import_key=fingerprint, defaults={
                'kind': 'social', 'title': cleaned['title'], 'body': cleaned['body'],
                'author': (INSTAGRAM_ACCOUNTS if instagram else SOCIAL_ACCOUNTS)[account]['name'], 'source_url': url, 'platform': platform,
                'source_metadata': {'raw_title': title[:4000], 'raw_excerpt': snippet[:16000],
                    'original_url': record['url'], 'account': account, 'normalization_version': cleaned['version'],
                    'account_platform': 'instagram' if instagram else 'x',
                    'parse_method': cleaned['method']}})
            created += int(added)
            if added:
                from .social_images import enrich_post_images
                enrich_post_images(post)
    status = {'state': 'partial' if failed and failed < len(batches) else 'error' if failed else 'ready',
              'created': created, 'found': found, 'checked_at': timezone.now().isoformat()}
    cache.set(STATUS_KEY, status, 86400)
    cache.set('community-account-cursor', offset + 1, 86400)
    if failed == len(batches):
        raise TavilySearchError('La recherche Tavily est temporairement indisponible.')
    return status


def repair_imported_posts():
    """Clean old imports in place, preserving raw evidence, likes and discussions."""
    cleaned_count, hidden = 0, 0
    for post in CommunityPost.objects.filter(import_key__isnull=False).iterator():
        metadata = dict(post.source_metadata or {})
        title = metadata.get('raw_title', post.title)
        excerpt = metadata.get('raw_excerpt', post.body)
        metadata.setdefault('raw_title', title)
        metadata.setdefault('raw_excerpt', excerpt)
        account = metadata.get('account') or account_from_url(metadata.get('original_url', post.source_url))
        instagram = metadata.get('account_platform') == 'instagram'
        # Legacy X URLs lost their handle. Recover attribution only when the page
        # title names an exact catalogue entry; this is not account verification.
        if not account:
            prefix = re.split(r'\s+(?:on X|sur X|on Twitter)\s*:', title, maxsplit=1)[0]
            normalize = lambda value: re.sub(r'\s+', '', value).casefold()
            account = next((handle for handle, data in SOCIAL_ACCOUNTS.items()
                            if normalize(prefix) == normalize(data['name'])), None)
        cleaned = extract_post(post.title, post.body) if instagram else extract_post(title, excerpt)
        if metadata.get('text_complete') and metadata.get('text_source')=='x_embed':
            # Never replace recovered full native text with an older indexed excerpt.
            cleaned={'title':post.title,'body':post.body,'version':metadata.get('normalization_version',2),'method':'native_post'}
        if platform_excluded(post.source_url) or post.platform in EXCLUDED_PLATFORMS or account not in (INSTAGRAM_ACCOUNTS if instagram else SOCIAL_ACCOUNTS) or not cleaned:
            metadata['exclusion_reason'] = 'excluded_platform' if platform_excluded(post.source_url) else 'unselected_or_unclear_source'
            CommunityPost.objects.filter(pk=post.pk).update(is_visible=False, source_metadata=metadata)
            hidden += 1
            continue
        metadata.update(account=account, normalization_version=cleaned['version'], parse_method=cleaned['method'])
        CommunityPost.objects.filter(pk=post.pk).update(title=cleaned['title'], body=cleaned['body'],
            author=(INSTAGRAM_ACCOUNTS if instagram else SOCIAL_ACCOUNTS)[account]['name'], source_metadata=metadata)
        cleaned_count += 1
    return {'cleaned': cleaned_count, 'hidden': hidden}


def refresh_social_if_due():
    if not getattr(settings, 'COMMUNITY_SOCIAL_DISCOVERY', True) or not getattr(settings, 'TAVILY_API_KEY', ''):
        return
    interval = max(300, getattr(settings, 'COMMUNITY_SOCIAL_REFRESH_SECONDS', 900))
    if not cache.add('community-social-refresh', True, interval):
        return
    cache.set(STATUS_KEY, {'state': 'refreshing'}, 86400)

    def refresh():
        close_old_connections()
        try:
            import_social_posts()
        except Exception:
            cache.set(STATUS_KEY, {'state': 'error', 'checked_at': timezone.now().isoformat()}, 86400)
            logger.warning('Social discovery failed; existing community posts remain available.')
        finally:
            close_old_connections()
    threading.Thread(target=refresh, name='community-social', daemon=True).start()


def discovery_status():
    if not getattr(settings, 'COMMUNITY_SOCIAL_DISCOVERY', True):
        return {'state': 'disabled'}
    if not getattr(settings, 'TAVILY_API_KEY', ''):
        return {'state': 'unconfigured'}
    return cache.get(STATUS_KEY, {'state': 'pending'})
