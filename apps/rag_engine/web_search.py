"""Tavily search and extraction, with credentials kept on the server."""

import logging
import re
from datetime import datetime
from urllib.parse import urlsplit, urljoin

import requests
from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)


def article_image(content, page_url):
    """Only use image URLs found inside this result's own extracted article."""
    for match in re.finditer(r'!\[[^\]]*\]\(<?([^\s\)<>]+)>?(?:\s+"[^"]*")?\)', content or ''):
        url = urljoin(page_url, match.group(1))
        if urlsplit(url).scheme in ('https', 'http') and not any(word in url.lower() for word in ('favicon', 'logo', 'avatar', 'tracking', '.svg')):
            return url
    return ''


class TavilySearchError(RuntimeError):
    pass


class TavilyDRCSearchTool:
    def __init__(self, max_results=4):
        self.max_results = max_results
        self._api_key = getattr(settings, 'TAVILY_API_KEY', '')
        # Retain the results interface used by official-source discovery.
        self.wrapper = self if self._api_key else None

    def _post(self, endpoint, payload):
        if not self._api_key:
            raise TavilySearchError('Clé Tavily non configurée sur le serveur.')
        try:
            response = requests.post(
                'https://api.tavily.com/' + endpoint,
                headers={'Authorization': 'Bearer ' + self._api_key, 'Content-Type': 'application/json'},
                json=payload, timeout=(5, 40),
            )
            if not response.ok:
                raise TavilySearchError(f'Tavily est indisponible (HTTP {response.status_code}).')
            return response.json()
        except (requests.RequestException, ValueError):
            raise TavilySearchError('Connexion Tavily indisponible. Réessayez.') from None

    def results(self, query, max_results=None, include_domains=None, time_range=None):
        payload = {'query': query, 'max_results': max_results or self.max_results,
                   'search_depth': getattr(settings, 'TAVILY_SEARCH_DEPTH', 'basic'),
                   'include_answer': False, 'include_raw_content': 'markdown', 'include_favicon': True}
        if include_domains:
            payload['include_domains'] = include_domains
        if time_range:
            payload['time_range'] = time_range
        response = self._post('search', payload)
        results = []
        for result in response.get('results', []):
            url = result.get('url', '')
            if urlsplit(url).scheme not in ('https', 'http'):
                continue
            results.append({'title': result.get('title', ''), 'url': url, 'link': url,
                            'snippet': result.get('content', ''), 'raw_content': result.get('raw_content') or '',
                            'published_at': result.get('published_date') or result.get('published_at') or '',
                            'favicon': result.get('favicon', '')})
        return results

    def extract(self, urls):
        return self._post('extract', {'urls': urls, 'extract_depth': 'advanced', 'format': 'markdown'})

    def search(self, query, drc_context=True):
        result = {'query': query, 'source': 'Tavily', 'structured': [], 'results_raw': '',
                  'verified_at': datetime.now().strftime('%d/%m/%Y')}
        try:
            recent = any(word in query.lower() for word in ('derni', 'récent', 'recent', 'actualit', 'aujourd', 'latest', 'habari', 'sango'))
            records = self.results(query + (' RDC' if drc_context else ''), **({'time_range': 'month'} if recent else {}))
            result['structured'] = [{'title': item['title'], 'url': item['url'],
                                     'snippet': item['snippet'], 'raw_content': item['raw_content'][:12000], 'favicon': item['favicon'],
                                     'published_at': item['published_at'], 'retrieved_at': timezone.now().isoformat(),
                                     'image_url': article_image(item['raw_content'], item['url'])} for item in records]
            result['results_raw'] = '\n\n'.join(f"{item['title']}\nURL: {item['url']}\n{item['snippet']}" for item in records)
            result['status'] = 'success' if records else 'warning'
        except TavilySearchError as error:
            logger.warning('Tavily search unavailable')
            result.update(status='error', error=str(error))
        return result
