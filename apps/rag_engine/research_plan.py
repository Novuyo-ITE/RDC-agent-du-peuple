"""Build a bounded, step-back research plan for the main assistant."""
import json
import logging
import re
from concurrent.futures import ThreadPoolExecutor

from django.conf import settings
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_ollama import ChatOllama
from .geographic_scope import DRC_SCOPE_INSTRUCTIONS
from django.utils import timezone

logger = logging.getLogger(__name__)


def research_queries(question):
    """Search the original question plus four complementary perspectives.

    The model's generalization is used only as a search query, never as evidence.
    A deterministic plan keeps research available if planning fails.
    """
    question = ' '.join(question.split())[:500]
    from .news_answers import news_question
    is_news = news_question(question)
    today = timezone.localdate().isoformat()
    fallback = [f'{question} {suffix}' for suffix in (
        'contexte général principes', 'faits données sources',
        'analyses perspectives', 'dernières informations actualités RDC')]
    news_directive = ''
    if is_news:
        fallback = [f'{question} RDC {today} {suffix}' for suffix in (
            'dernières publications faits datés', 'politique économie société dernières nouvelles',
            'sécurité santé provinces derniers développements', 'communiqués et reportages récents')]
        news_directive = (
            f'Date actuelle : {today}. Pour cette question d’actualité, recherche des articles récents '
            'et datés sur le sujet demandé en RDC, plutôt que des principes abstraits. '
            'Pour un panorama général, diversifie les thèmes et les médias. ')
    candidates = []
    if getattr(settings, 'TAVILY_API_KEY', ''):
        try:
            from .services import get_chat_ollama, get_llm_provider
            if get_llm_provider() == 'gemini':
                planner = get_chat_ollama().bind(options={'temperature': 0.1, 'num_predict': 512})
            else:
                planner = ChatOllama(
                    base_url=getattr(settings, 'OLLAMA_BASE_URL', 'http://localhost:11434'),
                    model=getattr(settings, 'OLLAMA_MODEL', 'qwen2.5-coder:14b'),
                    keep_alive=getattr(settings, 'OLLAMA_KEEP_ALIVE', '24h'),
                    num_ctx=getattr(settings, 'OLLAMA_NUM_CTX', 8192),
                    temperature=0.1, num_predict=220,
                    client_kwargs={'timeout': getattr(settings, 'OLLAMA_REQUEST_TIMEOUT', 300)})
            response = planner.invoke([
                SystemMessage(content=(
                    DRC_SCOPE_INSTRUCTIONS + '\n' +
                    news_directive +
                    'Planifie une recherche documentaire par abstraction (step-back). '
                    'À partir de la question, formule quatre requêtes de recherche distinctes : '
                    'une sur le contexte ou principe général sous-jacent, une sur les faits ou données, '
                    'une sur des analyses ou points de vue et une sur les développements récents. '
                    'Conserve le sujet, les noms et le contexte géographique pertinents. '
                    'Cet assistant sert surtout la RDC : précise ce contexte lorsqu’il est implicite, '
                    'sans l’imposer aux questions qui concernent clairement un autre lieu. '
                    'Ne réponds pas à la question et ne suppose aucun fait. '
                    'Retourne seulement un tableau JSON de quatre chaînes.')),
                HumanMessage(content=question),
            ])
            content = response.content if isinstance(response.content, str) else ''
            match = re.search(r'\[.*?\]', content, re.S)
            parsed = json.loads(match.group(0)) if match else []
            if isinstance(parsed, list):
                candidates = [item.strip()[:800] for item in parsed if isinstance(item, str) and item.strip()]
        except Exception:
            logger.warning('Research planning unavailable; using the default research perspectives.')
    queries, seen = [question], {question.casefold()}
    for candidate in candidates + fallback:
        if candidate.casefold() not in seen:
            queries.append(candidate)
            seen.add(candidate.casefold())
        if len(queries) == 5:
            break
    return queries


def search_perspectives(search_tool, queries, social_search=None):
    """Run independent searches concurrently and keep partial successes."""
    results, social = [], []
    with ThreadPoolExecutor(max_workers=len(queries) + bool(social_search)) as pool:
        futures = [pool.submit(search_tool.search, query, drc_context=True) for query in queries]
        social_future = pool.submit(social_search) if social_search else None
        for future in futures:
            try:
                result = future.result()
                results.append(result if isinstance(result, dict) else {})
            except Exception:
                logger.warning('One research search failed; continuing with the other results.')
                results.append({})
        if social_future:
            try:
                social = social_future.result() or []
            except Exception:
                logger.warning('Public X research unavailable.')
    return results, social


def merge_web_results(results, limit=10):
    """Deduplicate URLs and interleave perspectives before applying the context limit."""
    from urllib.parse import urlsplit, urlunsplit
    groups = [result.get('structured') or [] for result in results if result.get('status') == 'success']
    merged, seen = [], set()
    for position in range(max((len(group) for group in groups), default=0)):
        for group in groups:
            if position >= len(group):
                continue
            item = group[position]
            url = item.get('url', '')
            parts = urlsplit(url)
            if parts.scheme not in ('http', 'https') or not parts.hostname:
                continue
            if parts.hostname.lower().removeprefix('www.') in ('x.com', 'twitter.com', 'mobile.x.com', 'mobile.twitter.com'):
                continue
            key = urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path.rstrip('/'), parts.query, ''))
            if key in seen:
                continue
            seen.add(key)
            merged.append(item)
            if len(merged) >= limit:
                return merged
    return merged
