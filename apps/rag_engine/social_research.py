"""Find public X posts for news questions without treating posts as verified facts."""
import logging
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

from django.conf import settings
from django.db.models import Q
from django.utils import timezone

from .models import CommunityPost
from .source_briefs import source_excerpt
from .web_search import TavilyDRCSearchTool, TavilySearchError
from apps.web_ui.social_accounts import SOCIAL_ACCOUNTS, account_from_url
from apps.web_ui.social_images import fetch_x_photos, valid_x_photo
from apps.web_ui.social_sources import canonical_post_url
from apps.web_ui.social_text import extract_post

logger = logging.getLogger(__name__)


def news_request(query):
    return bool(re.search(r'actualit|derni[eè]r|nouvelle|r[eé]cent|aujourd|news|latest|habari|sango|twitter|tweeter|x\.com', query, re.I))


def stored_x_sources(query_words):
    posts = CommunityPost.objects.filter(kind='social', platform='X / Twitter', is_visible=True,
        import_key__isnull=False, created_at__gte=timezone.now() - timedelta(days=30))
    if query_words:
        terms = Q()
        for word in query_words:
            terms |= Q(title__icontains=word) | Q(body__icontains=word)
        posts = posts.filter(terms)
    found = []
    for post in posts.order_by('-created_at')[:30]:
        metadata = post.source_metadata or {}
        account = metadata.get('account', '').lower()
        original_url = metadata.get('original_url', '')
        if account not in SOCIAL_ACCOUNTS or account_from_url(original_url) != account or not canonical_post_url(post.source_url):
            continue
        # A linked article's image is not the post's own photo.
        photos = [url for url in metadata.get('images', []) if valid_x_photo(url)] if metadata.get('image_source') != 'linked_article' else []
        found.append({'title': post.title, 'institution': SOCIAL_ACCOUNTS[account]['name'],
            'url': post.source_url, 'image_url': photos[0] if photos else '',
            'excerpt': source_excerpt(post.body), 'excerpt_label': 'Publication X · contenu non vérifié',
            'text': post.body[:6000], 'source_kind': 'social', 'published_at': '',
            'retrieved_at': post.created_at.isoformat()})
        if len(found) == 3:
            break
    return found


def search_live_x(query):
    """Search selected accounts, then fetch only each post's own verified media."""
    if not getattr(settings, 'TAVILY_API_KEY', ''):
        return []
    try:
        records = TavilyDRCSearchTool(max_results=5).results(
            query + ' RDC', include_domains=['x.com', 'twitter.com'], time_range='week')
    except TavilySearchError:
        logger.warning('Recherche X indisponible ; utilisation des sources enregistrées.')
        return []
    candidates, seen = [], set()
    for item in records:
        original = item.get('url', '')
        account = account_from_url(original)
        canonical = canonical_post_url(original)
        cleaned = extract_post(item.get('title', ''), item.get('snippet', ''))
        if not account or not canonical or not cleaned or canonical[0] in seen:
            continue
        seen.add(canonical[0])
        candidates.append((canonical[0], account, cleaned, item))
        if len(candidates) == 3:
            break
    if not candidates:
        return []
    with ThreadPoolExecutor(max_workers=3) as pool:
        photos = list(pool.map(lambda item: fetch_x_photos(item[0], item[1]), candidates))
    results = []
    for (url, account, cleaned, item), images in zip(candidates, photos):
        body = cleaned['body']
        results.append({'title': cleaned['title'], 'institution': SOCIAL_ACCOUNTS[account]['name'],
            'url': url, 'image_url': next((image for image in images if valid_x_photo(image)), ''),
            'excerpt': source_excerpt(body), 'excerpt_label': 'Extrait X indexé · contenu non vérifié',
            'text': body[:6000], 'source_kind': 'social', 'published_at': item.get('published_at', ''),
            'retrieved_at': timezone.now().isoformat()})
    return results
