"""
Scrapers & Extractors for DRC Government and Public News Portals.
Targets:
- presidence.cd / primature.cd (Official government communications)
- radiookapi.net (UN/DRC verified news portal)
- actualite.cd (DRC political, judicial, and economic news)
"""

import logging
import requests
from bs4 import BeautifulSoup
from typing import List, Dict, Any, Optional
from datetime import datetime

logger = logging.getLogger(__name__)

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) DRC-Gov-Digital-Assistant/1.0 (+https://presidence.cd)'
}


class BasePortalExtractor:
    """Base class for DRC portal web crawlers."""
    def __init__(self, timeout: int = 15):
        self.timeout = timeout

    def fetch_soup(self, url: str) -> Optional[BeautifulSoup]:
        try:
            resp = requests.get(url, headers=HEADERS, timeout=self.timeout)
            resp.raise_for_status()
            return BeautifulSoup(resp.content, 'html.parser')
        except Exception as e:
            logger.error(f"Failed to fetch {url}: {e}")
            return None


class RadioOkapiExtractor(BasePortalExtractor):
    """Extractor for Radio Okapi (UN Mission & Public News in DRC)."""
    BASE_URL = "https://www.radiookapi.net"

    def extract_recent_articles(self, limit: int = 5) -> List[Dict[str, Any]]:
        articles = []
        soup = self.fetch_soup(f"{self.BASE_URL}/actualite")
        if not soup:
            return articles

        items = soup.select(".views-row, article")[:limit]
        for item in items:
            title_tag = item.select_one("h2 a, h3 a, .title a")
            if not title_tag:
                continue

            title = title_tag.get_text(strip=True)
            link = title_tag.get("href", "")
            if link and not link.startswith("http"):
                link = f"{self.BASE_URL}{link}"

            snippet_tag = item.select_one(".field-content, .summary, p")
            snippet = snippet_tag.get_text(strip=True) if snippet_tag else ""

            articles.append({
                "title": title,
                "url": link,
                "institution": "Radio Okapi (Actualité RDC)",
                "raw_text": snippet,
                "source_type": "actualite_officielle",
                "language": "fr",
                "scraped_at": datetime.now().isoformat()
            })
        return articles


class PresidenceRdcExtractor(BasePortalExtractor):
    """Extractor for official communications from presidence.cd."""
    BASE_URL = "https://presidence.cd"

    def extract_press_releases(self, limit: int = 5) -> List[Dict[str, Any]]:
        articles = []
        soup = self.fetch_soup(self.BASE_URL)
        if not soup:
            return articles

        cards = soup.select("article, .post-item, .news-item")[:limit]
        for card in cards:
            title_tag = card.select_one("h2, h3, a")
            if not title_tag:
                continue

            title = title_tag.get_text(strip=True)
            link = title_tag.get("href", "")
            if link and not link.startswith("http"):
                link = f"{self.BASE_URL}/{link.lstrip('/')}"

            desc_tag = card.select_one("p")
            desc = desc_tag.get_text(strip=True) if desc_tag else ""

            articles.append({
                "title": title,
                "url": link,
                "institution": "Présidence de la République Démocratique du Congo",
                "raw_text": desc,
                "source_type": "presidence",
                "language": "fr",
                "scraped_at": datetime.now().isoformat()
            })
        return articles

