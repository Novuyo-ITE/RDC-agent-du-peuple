"""
Real DRC News Fetcher — pulls live RSS feeds from verified Congolese news outlets.

Sources:
  - Radio Okapi (UN-backed public radio, most reliable)
  - Actualite.cd
  - 7sur7.cd
  - CongoIndependant.com
  - Desc-Wondo.org
  - Le Phare RDC

Run: python manage.py fetch_drc_news
"""

import re
import logging
import feedparser
import urllib.request
from datetime import datetime, timezone as dt_timezone
from email.utils import parsedate_to_datetime
from django.core.management.base import BaseCommand
from django.utils.text import slugify
from django.utils import timezone

try:
    from bs4 import BeautifulSoup
    BS4_OK = True
except ImportError:
    BS4_OK = False

from apps.rag_engine.models import OfficialNews
from apps.rag_engine.article_content import fetch_article_body

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────────────
# Verified DRC RSS feeds — ordered by reliability / editorial quality
# ──────────────────────────────────────────────────────────────────────────────
DRC_RSS_SOURCES = [
    {
        "name": "Radio Okapi",
        "url": "https://www.radiookapi.net/feed",
        "category_default": "securite",
        "region_default": "National",
    },
    {
        "name": "Radio Okapi (FeedBurner)",
        "url": "http://feeds.feedburner.com/radiookapi/actu?format=xml",
        "category_default": "securite",
        "region_default": "National",
    },
    {
        "name": "Actualite.cd",
        "url": "https://actualite.cd/feed",
        "category_default": "gouvernement",
        "region_default": "National",
    },
    {
        "name": "Congo Indépendant",
        "url": "https://www.congoindependant.com/feed/",
        "category_default": "gouvernement",
        "region_default": "National",
    },
    {
        "name": "La Sentinelle",
        "url": "https://lasentinelle.cd/feed/",
        "category_default": "societe",
        "region_default": "National",
    },
    {
        "name": "Sentinel DRC - La Sentinelle des Ressources Naturelles",
        "url": "https://sentineldrc.org/feed/",
        "category_default": "mines",
        "region_default": "National",
    },
    {
        "name": "Sentinelle RDC - Veille strategique",
        "url": "https://www.sentinelle-rdc.com/",
        "category_default": "gouvernement",
        "region_default": "National",
        # No public RSS feed; the article API requires authentication (HTTP 401).
        "enabled": False,
        "disabled_reason": "Article access requires an authenticated integration; no public RSS feed.",
    },
    {
        "name": "RFI Afrique",
        "url": "https://www.rfi.fr/fr/afrique/rss",
        "category_default": "international",
        "category_override": "international",
        "region_default": "National",
    },
    {
        "name": "Le Phare RDC",
        "url": "https://www.lephareonline.net/feed/",
        "category_default": "gouvernement",
        "region_default": "National",
    },
    {
        "name": "Desc-Wondo",
        "url": "https://desc-wondo.org/feed/",
        "category_default": "securite",
        "region_default": "Est de la RDC",
        "skip_ssl": True,
    },
]

# ──────────────────────────────────────────────────────────────────────────────
# Keyword → category & region mapping
# ──────────────────────────────────────────────────────────────────────────────
CATEGORY_KEYWORDS = {
    "securite": [
        "fardc", "m23", "adf", "fdlr", "codeco", "securite", "sécurité", "guerre",
        "combat", "militaire", "offensive", "attaque", "armée", "rebelle", "coalition",
        "nord-kivu", "ituri", "goma", "sake", "beni", "bunia", "masisi", "rutshuru",
        "djugu", "luanda", "ceasefire", "cessez-le-feu", "samidrc", "monusco",
        "neutralis", "operation militaire", "état de siège", "siège",
    ],
    "gouvernement": [
        "gouvernement", "conseil des ministres", "premier ministre", "primature",
        "présidence", "president", "sénat", "assemblée nationale", "parlement",
        "ministre", "décret", "ordonnance", "nomination", "réforme", "tshisekedi",
        "kabila", "politique", "opposition", "kabund", "katumbi",
    ],
    "economie": [
        "économie", "bcc", "banque centrale", "cdf", "franc congolais", "inflation",
        "budget", "investissement", "croissance", "pib", "taux", "dette", "fmi",
        "banque mondiale", "bourse", "marché", "finances", "trésor", "commerce",
    ],
    "mines": [
        "mines", "cobalt", "coltan", "cuivre", "or minier", "diamant", "minerai",
        "3t", "étain", "tungstène", "tantale", "arsp", "ceec", "katanga",
        "lualaba", "kamoto", "ivanhoe", "glencore", "kinross", "extraction",
    ],
    "diplomatie": [
        "diplomatie", "diplomatique", "accord", "traité", "union africaine",
        "nations unies", "onu", "usa", "états-unis", "union européenne",
        "angola", "rwanda", "burundi", "ouganda", "processus de luanda",
        "nairobi", "addis", "ambassade", "international",
    ],
    "justice": [
        "justice", "tribunal", "cour", "parquet", "arrêt", "condamné", "peine",
        "corruption", "détournement", "arrestation", "procès", "droit", "magistrat",
        "judiciaire", "prison", "détenu",
    ],
    "societe": [
        "santé", "education", "école", "hôpital", "vaccination", "mpox", "choléra",
        "ebola", "société", "humanitaire", "déplacé", "réfugié", "aide", "pam",
        "unicef", "infrastructure", "route", "pont", "électricité", "eau",
        "drépanocytose", "journaliste", "médias",
    ],
}

# Articles matching these patterns are NOT DRC governance news — skip them
IRRELEVANT_PATTERNS = [
    r"\bD\d\s+(Belgique|France|Suisse|Pologne|Espagne|Angleterre|Italie|Allemagne)\b",
    r"\bNorwich\b", r"\bPremier League\b", r"\bChampions League\b",
    r"\bLigue 1\b", r"\bBundesliga\b", r"\bSerie A\b",
    r"\bmanchester\b", r"\bbayern\b", r"\bbarcelona\b", r"\breal madrid\b",
    r"\bWidzew\b", r"\bSaint.Trond\b", r"\bYoung Boys\b",
    r"\b(football|soccer|basketbal|tennis|sport)\s+(club|score|match|resultat)\b",
    r"(?i)\b(horoscope|météo|recette|cuisine|mode|beauté)\b",
]

REGION_KEYWORDS = {
    "Nord-Kivu": ["nord-kivu", "goma", "sake", "masisi", "rutshuru", "walikale", "beni", "butembo"],
    "Sud-Kivu": ["sud-kivu", "bukavu", "uvira", "baraka", "shabunda", "mwenga"],
    "Ituri": ["ituri", "bunia", "djugu", "irumu", "aru", "mahagi"],
    "Kinshasa": ["kinshasa", "capitale", "limete", "gombe", "kasa-vubu"],
    "Katanga": ["katanga", "lubumbashi", "kolwezi", "likasi", "kamina", "lualaba"],
    "Est de la RDC": ["est de la rdc", "est du congo", "eastern drc", "kivu"],
    "Équateur": ["équateur", "mbandaka", "ingende"],
    "Kasaï": ["kasaï", "kananga", "mbuji-mayi", "tshikapa"],
    "Maniema": ["maniema", "kindu"],
    "Kongo Central": ["kongo central", "matadi", "boma"],
}

# Articles matching these patterns are sports/entertainment — skip them
IRRELEVANT_PATTERNS = [
    r"(?i)\bD\d\s+(Belgique|France|Suisse|Pologne|Espagne|Angleterre|Italie|Allemagne)\b",
    r"(?i)\bNorwich\s*City\b",
    r"(?i)\b(Premier League|Ligue 1|Bundesliga|Serie A|Champions League|Europa League)\b",
    r"(?i)\b(Widzew|Saint.Trond|Young Boys|Anderlecht|Club Bruges)\b",
    r"(?i)\b(Manchester|Bayern|Barcelona|Real Madrid|PSG|Arsenal)\b",
    r"(?i)\b(horoscope|recette de cuisine|mode fashion|beauté)\b",
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8",
}


def _is_irrelevant(title: str, summary: str) -> bool:
    """Returns True if the article is clearly not DRC governance/news content."""
    combined = (title + " " + summary).lower()
    for pattern in IRRELEVANT_PATTERNS:
        if re.search(pattern, title, re.IGNORECASE):
            return True
    # Skip pure sports scores / European football
    sport_leagues = ["d1 belgique", "d1 france", "d1 suisse", "d1 pologne", "d1 espagne",
                     "premier league", "ligue 1", "bundesliga", "serie a", "champions league"]
    for league in sport_leagues:
        if league in combined:
            return True
    return False


def _detect_category(text: str, default: str) -> str:
    t = text.lower()
    for cat, kws in CATEGORY_KEYWORDS.items():
        if any(k in t for k in kws):
            return cat
    return default


def _detect_region(text: str, default: str) -> str:
    t = text.lower()
    for region, kws in REGION_KEYWORDS.items():
        if any(k in t for k in kws):
            return region
    return default


def _parse_date(entry) -> datetime:
    """Returns an aware datetime from an RSS entry, falling back to now."""
    for attr in ("published_parsed", "updated_parsed"):
        val = getattr(entry, attr, None)
        if val:
            try:
                return datetime(*val[:6], tzinfo=dt_timezone.utc)
            except Exception:
                pass
    # Try string fallbacks
    for attr in ("published", "updated"):
        raw = getattr(entry, attr, None)
        if raw:
            try:
                return parsedate_to_datetime(raw).astimezone(dt_timezone.utc)
            except Exception:
                pass
    return datetime.now(dt_timezone.utc)


def _extract_image_from_entry(entry) -> str:
    """Tries multiple RSS fields to find a real image URL."""
    # 1. media:content (most common in WordPress feeds)
    media = getattr(entry, "media_content", None)
    if media:
        for m in media:
            url = m.get("url", "")
            if url and _is_valid_image_url(url):
                return url

    # 2. media:thumbnail
    thumb = getattr(entry, "media_thumbnail", None)
    if thumb:
        for t in thumb:
            url = t.get("url", "")
            if url and _is_valid_image_url(url):
                return url

    # 3. enclosures
    for enc in getattr(entry, "enclosures", []):
        url = enc.get("href", "") or enc.get("url", "")
        if url and _is_valid_image_url(url):
            return url

    # 4. Parse <img> from summary/content HTML
    for field in ("summary", "content"):
        html = ""
        if field == "content":
            content_list = getattr(entry, "content", [])
            html = content_list[0].get("value", "") if content_list else ""
        else:
            html = getattr(entry, "summary", "")
        if html and BS4_OK:
            soup = BeautifulSoup(html, "html.parser")
            img = soup.find("img")
            if img:
                src = img.get("src") or img.get("data-src") or ""
                if src and _is_valid_image_url(src):
                    return src
        # Regex fallback
        if html:
            match = re.search(r'<img[^>]+src=["\']([^"\']+)["\']', html, re.IGNORECASE)
            if match:
                url = match.group(1)
                if _is_valid_image_url(url):
                    return url

    return ""


def _is_valid_image_url(url: str) -> bool:
    if not url or not url.startswith(("http://", "https://")):
        return False
    lower = url.lower()
    # Accept common image extensions
    if any(ext in lower for ext in (".jpg", ".jpeg", ".png", ".webp", ".gif")):
        return True
    # WordPress uploads paths often lack extension in query params
    if "wp-content/uploads" in lower:
        return True
    return False


def _scrape_article_image(url: str, timeout: int = 5) -> str:
    """Fetches the article page and extracts the first meaningful image."""
    if not url or not BS4_OK:
        return ""
    try:
        import ssl
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
            html = resp.read().decode("utf-8", errors="ignore")
        soup = BeautifulSoup(html, "html.parser")

        # Prefer Open Graph og:image
        og = soup.find("meta", property="og:image")
        if og and og.get("content"):
            url_og = og["content"]
            if _is_valid_image_url(url_og):
                return url_og

        # Try Twitter card
        tw = soup.find("meta", attrs={"name": "twitter:image"})
        if tw and tw.get("content"):
            if _is_valid_image_url(tw["content"]):
                return tw["content"]

        # Try first large <img> inside article/main
        for tag in ("article", "main", "div"):
            block = soup.find(tag)
            if block:
                for img in block.find_all("img"):
                    src = img.get("src") or img.get("data-src") or ""
                    if _is_valid_image_url(src):
                        return src
    except Exception as e:
        logger.debug(f"Image scrape failed for {url}: {e}")
    return ""


def _clean_html(html: str) -> str:
    """Strips HTML tags and normalizes whitespace."""
    if not html:
        return ""
    if BS4_OK:
        soup = BeautifulSoup(html, "html.parser")
        text = soup.get_text(separator=" ")
    else:
        text = re.sub(r"<[^>]+>", " ", html)
    return re.sub(r"\s+", " ", text).strip()


def fetch_feed(source: dict, max_items: int = 15, stdout=None) -> int:
    """Fetches one RSS source and saves new/updated articles. Returns count saved."""
    if not source.get("enabled", True):
        if stdout:
            stdout.write(f"    [SKIP] {source['name']}: {source.get('disabled_reason', 'Source disabled.')}")
        return 0

    feed_url = source["url"]
    source_name = source["name"]
    cat_default = source["category_default"]
    region_default = source["region_default"]

    if stdout:
        stdout.write(f"\n  Fetching: {source_name} — {feed_url}")

    try:
        # Use urllib with custom headers; bypass SSL verification for sites with cert issues
        import ssl
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        req = urllib.request.Request(feed_url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=10, context=ctx) as resp:
            raw = resp.read()
        feed = feedparser.parse(raw)
    except Exception as e:
        if stdout:
            stdout.write(f"    [SKIP] Could not reach {feed_url}: {e}")
        return 0

    if feed.bozo and not feed.entries:
        if stdout:
            stdout.write(f"    [SKIP] Malformed feed or no entries.")
        return 0

    saved = 0
    for entry in feed.entries[:max_items]:
        title = _clean_html(getattr(entry, "title", "")).strip()
        if not title or len(title) < 10:
            continue

        link = getattr(entry, "link", "") or getattr(entry, "id", "")
        slug = slugify(title)[:250]
        if not slug:
            continue

        # Skip if already in DB (by slug)
        if OfficialNews.objects.filter(slug=slug).exists():
            continue

        # Build summary from RSS description/summary
        raw_summary = getattr(entry, "summary", "")
        summary_text = _clean_html(raw_summary)[:400]

        # Skip irrelevant content (sports scores, European football, etc.)
        if _is_irrelevant(title, summary_text):
            continue

        # Build full content
        content_list = getattr(entry, "content", [])
        if content_list:
            raw_content = content_list[0].get("value", raw_summary)
        else:
            raw_content = raw_summary
        full_text = fetch_article_body(link) or _clean_html(raw_content)

        from apps.rag_engine.news_policy import news_allowed
        if not news_allowed(source_name, link or feed_url, title, summary_text, full_text):
            continue

        if not summary_text and full_text:
            summary_text = full_text[:300]

        # Date
        pub_date = _parse_date(entry)

        # Detect category & region from title + summary
        combined_text = f"{title} {summary_text}"
        category = source.get("category_override") or _detect_category(combined_text, cat_default)
        region = _detect_region(combined_text, region_default)

        # Image — try RSS first, then scrape article page
        image_url = _extract_image_from_entry(entry)
        if not image_url and link:
            image_url = _scrape_article_image(link)

        OfficialNews.objects.create(
            title=title,
            slug=slug,
            category=category,
            source_name=source_name,
            source_url=link or feed_url,
            image_url=image_url,
            summary=summary_text,
            full_content=full_text,
            region=region,
            published_at=pub_date,
            is_verified=True,
        )
        saved += 1
        if stdout:
            stdout.write(f"    [+] {title[:70]}")

    return saved


class Command(BaseCommand):
    help = "Fetches real live news from verified Congolese RSS feeds and stores them."

    def add_arguments(self, parser):
        parser.add_argument(
            "--max-per-source",
            type=int,
            default=15,
            help="Max articles to fetch per RSS source (default: 15).",
        )
        parser.add_argument(
            "--clear-dummy",
            action="store_true",
            help="Delete all existing (seeded) news before fetching real ones.",
        )

    def handle(self, *args, **options):
        max_per = options["max_per_source"]
        clear_dummy = options["clear_dummy"]

        if clear_dummy:
            deleted, _ = OfficialNews.objects.all().delete()
            self.stdout.write(self.style.WARNING(f"Cleared {deleted} existing news records."))

        self.stdout.write(
            self.style.HTTP_INFO(
                f"\n=== DRC Live News Fetcher — {len(DRC_RSS_SOURCES)} sources, max {max_per}/source ===\n"
            )
        )

        total = 0
        for source in DRC_RSS_SOURCES:
            count = fetch_feed(source, max_items=max_per, stdout=self.stdout)
            total += count
            if count:
                self.stdout.write(self.style.SUCCESS(f"    => Saved {count} new articles from {source['name']}"))

        self.stdout.write(
            self.style.SUCCESS(f"\n[OK] Total new articles saved: {total}\n")
        )
        self.stdout.write(
            f"Total in DB: {OfficialNews.objects.count()} verified news articles."
        )
