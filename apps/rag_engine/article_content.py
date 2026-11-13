"""Extract readable article text from publisher pages."""

import logging

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


def extract_article_body(html):
    soup = BeautifulSoup(html, 'html.parser')
    for node in soup.select('script, style, nav, footer, aside, form, .sharedaddy, .related-posts, .social-share, .comments, #comments'):
        node.decompose()
    for selector in ('[itemprop="articleBody"]', '[id$="-corps"]', '.field--name-body', '.field-name-body',
                     '.entry-content', '.post-content', '.article-content', '.article-body',
                     '.td-post-content', 'article', 'main'):
        blocks = soup.select(selector)
        candidates = []
        for block in blocks:
            paragraphs = [node.get_text(' ', strip=True) for node in block.select('p, h2, h3, li, blockquote')
                          if not node.find_parent(['blockquote', 'li'])]
            text = '\n\n'.join(part for part in paragraphs if part)
            if not text:
                text = block.get_text('\n', strip=True)
            if len(text) >= 200:
                candidates.append(text)
        if candidates:
            return max(candidates, key=len)
    return ''


def fetch_article_body(url):
    if not url or not url.startswith(('http://', 'https://')):
        return ''
    try:
        response = requests.get(url, timeout=(5, 15), headers={
            'User-Agent': 'Mozilla/5.0 (compatible; DRCNewsReader/1.0)',
        })
        response.raise_for_status()
        if response.encoding == 'ISO-8859-1':
            response.encoding = response.apparent_encoding
        return extract_article_body(response.text)
    except requests.RequestException:
        logger.warning('Could not fetch article body from %s', url, exc_info=True)
        return ''
