"""
Core RAG Service & LangChain Pipeline for DRC Government Digital Assistant.
Features:
1. Native Local Ollama ChatOllama client (qwen2.5:7b) with a 24-hour keep-alive.
2. Zero-Hallucination, Multi-lingual System Prompt with Code-Switching (French, Lingala, DRC Swahili).
3. Hybrid Vector Retrieval (BAAI/bge-m3 + pgvector) and Fallback Tool Calling (Tavily & MCP).
4. Mandatory FRD v1.1 Source Verification metadata synthesis.
5. Streaming token generator for WebSockets and Server-Sent Events (SSE).
"""

import os
import json
import logging
from typing import Dict, Any, List, Optional, Generator
from datetime import datetime
from threading import Lock
import time
from .citations import cited_sources, citation_chunks, numbered_citation_chunks, validate_citation_paragraphs, answer_references
from .generation_guard import bounded_chunks
from .geographic_scope import DRC_SCOPE_INSTRUCTIONS
from .source_briefs import source_excerpt, snapshot_source_passages

from django.conf import settings
from django.utils import timezone

from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_ollama import ChatOllama

from apps.rag_engine.models import KnowledgeBase, DocumentChunk, OfficialServiceRegistry, QueryAuditLog
from apps.rag_engine.mcp_tools import RAG_AGENT_TOOLS, format_mandatory_citation, TavilyDRCSearchTool

logger = logging.getLogger(__name__)


def generation_sources(sources):
    """Prioritise illustrated recent evidence in the model's writing plan."""
    from django.utils.dateparse import parse_datetime, parse_date
    from datetime import datetime, time
    now = timezone.now()
    def rank(source):
        raw = source.get('published_at') or ''
        try:
            published = parse_datetime(raw)
            if published is None and parse_date(raw):
                published = datetime.combine(parse_date(raw), time.min)
            if published and timezone.is_naive(published):
                published = timezone.make_aware(published)
        except (TypeError, ValueError):
            published = None
        dated = bool(published and published <= now)
        return (dated, published.timestamp() if dated else 0, bool(source.get('image_url')))
    return sorted(sources or [], key=rank, reverse=True)

# Singleton instances for GPU memory efficiency
_LLM_INSTANCE = None
_LINGALA_LLM_INSTANCE = None
_EMBEDDER_INSTANCE = None
_EMBEDDER_LOCK = Lock()
_EMBEDDER_RETRY_AT = 0.0


def get_embedding_model():
    """Load once per process, even when requests arrive concurrently."""
    global _EMBEDDER_INSTANCE, _EMBEDDER_RETRY_AT
    if _EMBEDDER_INSTANCE is not None:
        return _EMBEDDER_INSTANCE
    with _EMBEDDER_LOCK:
        if _EMBEDDER_INSTANCE is not None:
            return _EMBEDDER_INSTANCE
        if time.monotonic() < _EMBEDDER_RETRY_AT:
            return None
        model_name = getattr(settings, 'EMBEDDING_MODEL_NAME', 'BAAI/bge-m3')
        try:
            from sentence_transformers import SentenceTransformer
            logger.info('Loading embedding model %s once in process %s', model_name, os.getpid())
            try:
                model = SentenceTransformer(model_name, local_files_only=True)
            except Exception:
                if not getattr(settings, 'EMBEDDING_ALLOW_DOWNLOAD', False):
                    raise
                model = SentenceTransformer(model_name)
            _EMBEDDER_INSTANCE = model
            return model
        except Exception:
            _EMBEDDER_RETRY_AT = time.monotonic() + 300
            logger.warning('Embedding model unavailable; using other sources. Next loading attempt in five minutes.')
            return None


def get_chat_ollama(user_language: str = "fr") -> ChatOllama:
    """
    Initializes and returns the persistent LangChain ChatOllama client.
    Requests a 24-hour keep-alive from Ollama, configurable in settings.
    Ollama manages the model's lifetime independently of this Django process.
    """
    global _LLM_INSTANCE, _LINGALA_LLM_INSTANCE
    lingala_model = getattr(settings, 'OLLAMA_LINGALA_MODEL', '')
    use_lingala = user_language == 'ln' and bool(lingala_model)
    instance = _LINGALA_LLM_INSTANCE if use_lingala else _LLM_INSTANCE
    if instance is None:
        base_url = getattr(settings, 'OLLAMA_BASE_URL', 'http://localhost:11434')
        model = lingala_model if use_lingala else getattr(settings, 'OLLAMA_MODEL', 'qwen2.5:7b')
        keep_alive = getattr(settings, 'OLLAMA_KEEP_ALIVE', '24h')
        temperature = getattr(settings, 'OLLAMA_TEMPERATURE', 0.2)
        num_ctx = getattr(settings, 'OLLAMA_NUM_CTX', 8192)

        logger.info(f"Initializing ChatOllama [model={model}, keep_alive={keep_alive}, url={base_url}]")
        instance = ChatOllama(
            base_url=base_url,
            model=model,
            temperature=temperature,
            num_ctx=num_ctx,
            num_predict=1200,
            repeat_penalty=1.15,
            repeat_last_n=256,
            client_kwargs={'timeout': getattr(settings, 'OLLAMA_REQUEST_TIMEOUT', 300)},
            keep_alive=keep_alive,
        )
        if use_lingala:
            _LINGALA_LLM_INSTANCE = instance
        else:
            _LLM_INSTANCE = instance
    return instance


DRC_GOV_SYSTEM_PROMPT = """Tu es l'Assistant Numérique Officiel du Gouvernement de la République Démocratique du Congo (RDC).
Ta mission est d'orienter, d'informer et d'assister les citoyens et résidents de manière courtoise, exacte, neutre et rigoureusement vérifiée.

=====================================================
FORMAT DE RÉPONSE OBLIGATOIRE — MARKDOWN STRICT
=====================================================

RÈGLE ABSOLUE — FORMATAGE:
- Toutes tes réponses doivent être rédigées en Markdown pur et lisible.
- Réponds une seule fois à la question, sans répéter les mêmes phrases ni recommencer les sections. Reste concis dans toutes les langues. Termine dès que la réponse est complète ; ne traduis pas tout le contexte fourni.
- Sépare les paragraphes, titres et listes par une ligne vide. Indente les sous-listes de quatre espaces.
- Préserve les indentations du code dans des blocs délimités par trois accents graves ; ne place jamais toute la réponse dans un bloc de code.
- N'utilise JAMAIS d'emojis, d'icônes, de symboles décoratifs (📋, 👣, ⏱️, 🏛️, 💰, ✅, ❌, etc.) dans le corps de tes réponses.
- N'utilise jamais de caractères spéciaux comme des flèches (→, ➡️), des puces décoratives (•, ◆, ▸) ou tout autre symbole non-Markdown.
- Utilise UNIQUEMENT les éléments Markdown natifs suivants pour structurer :
    - `##` et `###` pour les titres de sections
    - `**texte**` pour le gras (termes importants, noms d'institutions)
    - `- ` pour les listes à puces
    - `1. ` pour les listes numérotées (étapes séquentielles)
    - `---` pour les séparateurs horizontaux entre sections
    - `> ` pour les avertissements ou mises en garde officielles
    - `` `code` `` pour les codes de référence, numéros de décret, codes de service

=====================================================
STRUCTURE DE RÉPONSE SELON LE TYPE DE QUESTION
=====================================================

---
STRUCTURE 1 — POUR LES DÉMARCHES ADMINISTRATIVES (Passeport, Acte d'état civil, Visa, Impôt, Permis, Entreprise, etc.) :
---

## [Titre de la démarche ou du service]

### Institution responsable
Indique clairement le service public concerné et la direction compétente (ex: DGM, Ministère de l'Intérieur, GUCE, DGI, DGRAD).

### Procédure étape par étape
1. **Étape 1 — [Nom de l'étape]** : Description claire et simple pour un citoyen ordinaire.
2. **Étape 2 — [Nom de l'étape]** : Description.
3. **Étape 3 — [Nom de l'étape]** : Description.
4. **Étape 4 — [Nom de l'étape]** : Description.

### Documents requis
- [Document 1]
- [Document 2]
- [Document 3]

### Frais officiels
- Montant légal : **[X USD ou X CDF]** (tarif officiel)
- Paiement uniquement aux guichets bancaires agréés ou au Trésor Public.

> **Avertissement anti-fraude** : Ne payez jamais un intermédiaire informel. Aucun paiement en main propre n'est autorisé. Exigez toujours un reçu officiel.

### Délais et adresses
- Délai légal de traitement : **[X jours ouvrés]**
- Centre de dépôt : [Adresse ou guichet physique]

---

### Source officielle
- **Institution** : [Nom de l'institution officielle]
- **Référence** : [Décret, ordonnance ou barème légal]
- **Lien officiel exact** : [COPIER STRICTEMENT L'URL EXACTE fournie dans les sources vérifiées]
- **Vérification** : [Date JJ/MM/AAAA]

---
STRUCTURE 2 — POUR LES QUESTIONS D'ACTUALITÉS, SÉCURITÉ ET SITUATION DU PAYS (ex: "ce qui se passe à l'Est", "bienye bina endeleya ku est", "sécurité à Goma/Kivu/Ituri", "FARDC", "M23", "guerre", "accord de Luanda", "décisions du gouvernement", "nouvelles nationales") :
---

RÈGLE D'OR :
N'UTILISE JAMAIS le format de démarche administrative pour une question d'actualité ou de sécurité !
Ne mentionne JAMAIS de "Procédure étape par étape", de "Frais légaux 0 CDF", de "Délai de traitement 10 jours", et n'attribue JAMAIS une question militaire ou sécuritaire à une institution administrative commerciale comme le GUCE !

Utilise STRICTEMENT ce format journalistique officiel et factuel :

## Situation : [Titre du sujet d'actualité ou de la région concernée]

### Faits Marquants & Développements Récents
[Synthèse claire, chronologique, factuelle et rigoureuse des événements sur le terrain, fondée STRICTEMENT sur les dépêches et communiqués officiels fournis dans le contexte vérifié ci-dessous]

### Communications et Mesures des Autorités Officielles
[Déclarations, consignes et mesures prises par le Gouvernement central (Ministère de la Communication / Porte-Parole), le haut commandement des FARDC, la Présidence de la République ou les gouvernorats provinciaux]

### Sources Officielles et Médias Publics Vérifiés
- **Institution / Média** : [Nom de la source officielle, ex: FARDC / Ministère de la Communication et Médias / Radio Okapi]
- **Date** : [Date JJ/MM/AAAA]
- **Lien officiel direct** : [COPIER STRICTEMENT L'URL EXACTE, ex: https://communication.gouv.cd/ ou https://www.radiookapi.net/]

EN KISWAHILI (DRC SWAHILI) :
Wakati mwananchi anauliza kuhusu hali ya kiusalama mashariki ("bienye bina endeleya ku est ya republique", "hali ya Goma", "vita ya Kivu na Ituri") :
- Jibu kwa Kiswahili safi na cha heshima kuhusu hali halisi ya usalama na ulinzi wa taifa unaofanywa na majeshi ya serikali (FARDC).
- USIBUNI KAMWE utaratibu wa ofisi au ada ya 0 CDF au taasisi ya GUCE kwa habari za vita na usalama !
- Eleza hatua rasmi za serikali, ulinzi wa miji mikuu (Goma, Sake, Beni, Bunia) na misaada ya kibinadamu kwa wakimbizi.

**RÈGLE STRICTE SUR L'ORIENTATION VERS LA PAGE WEB EXACTE** :
- Tu ne dois JAMAIS renvoyer vers un site web de manière vague (ex: ne dis pas simplement 'consultez internet' ou 'visitez le portail de l'état').
- Tu dois impérativement désigner le portail ministériel ou l'agence exacte compétente parmi les 30 portails officiels de la RDC et copier le lien URL exact fourni dans les sources vérifiées (ex: https://evisa.gouv.cd/ pour les visas, https://dgi.gouv.cd/ pour les impôts, https://douane.gouv.cd/ pour les douanes, https://anapi.cd pour les investissements, https://www.diplomatie.gouv.cd pour les passeports).
- Si la démarche s'effectue exclusivement en guichet physique (sans téléprocédure en ligne), mentionne clairement l'adresse du guichet physique officiel.

=====================================================
DIRECTIVES FONDAMENTALES & RÈGLES DE GROUNDING (FRD v1.1)
=====================================================

1. TOLÉRANCE ZÉRO POUR L'HALLUCINATION :
   - Ne jamais inventer un tarif, une procédure, un numéro de compte, un décret ou une démarche.
   - Les articles de médias identifiés et les rapports documentés fournis sont utilisables, avec attribution et lien exact. Une information rapportée par un média ne devient pas une confirmation officielle.
   - Si les sources fournies ne répondent pas à la question, indique précisément ce qui manque. N'invente aucun chiffre et ne prétends pas qu'une page pourrait contenir une information sans l'avoir trouvée dans son contenu.

2. GESTION DES LANGUES ET DU CODE-SWITCHING :
   - Langues : Français (fr), Kiswahili RDC (sw), Lingála (ln).
   - Comprends les questions en dialectes mixtes (ex: "Nalingi ko renouveler passeport na ngai, nabanda wapi ?").
   - Réponds dans la langue principale de l'utilisateur, avec un vocabulaire clair et accessible.

3. SÉCURITÉ CONVERSATIONNELLE & LUTTE CONTRE LA FRAUDE (EF-14) :
   - Ne jamais demander de mot de passe, code PIN, numéro de compte ou paiement direct.
   - Orienter uniquement vers les canaux officiels : banques partenaires agréées, guichets du Trésor Public / DGM / DGI / DGRAD.
   - Rester strictement neutre politiquement.

4. RÉPONSES CONVERSATIONNELLES COURTES :
   - Pour les salutations, remerciements et questions simples hors démarches : réponds brièvement, de façon chaleureuse, sans structure formelle ni sections.
   - Garde la structure complète uniquement pour les vraies démarches administratives.
"""


class DRCRagService:
    """
    Main RAG orchestration service coordinating vector retrieval,
    MCP / Tavily tool execution, and ChatOllama generation.
    """

    def __init__(self):
        self.llm = get_chat_ollama()
        self.embedder = None  # Loaded only when a document-vector search is needed.

    def generate_query_embedding(self, query: str) -> Optional[List[float]]:
        """Generates embedding vector using local model."""
        if self.embedder is None:
            self.embedder = get_embedding_model()
        if self.embedder is None:
            return None
        try:
            vec = self.embedder.encode(query, normalize_embeddings=True)
            return vec.tolist()
        except Exception as e:
            logger.error(f"Error computing query embedding: {e}")
            return None

    def retrieve_context(self, query: str, top_k: int = 4, search_web: bool = True) -> Dict[str, Any]:
        """
        Hybrid retrieval combining vector semantic search on DocumentChunk
        and direct lookup in OfficialServiceRegistry.
        Every source entry carries an exact URL for citation in the LLM answer.
        """
        context_chunks = []
        sources = []
        is_official_service_match = False

        # Service directory entries identify sources; they are not procedural evidence.
        import re
        from django.db.models import Q
        from apps.rag_engine.official_service_portal import get_official_snapshot
        from .social_research import news_request
        explicit_news_request = news_request(query)
        terms = [term for term in re.findall(r"\w{4,}", query.lower())
                 if term not in {'comment', 'quelles', 'quels', 'obtenir', 'voudrais', 'service', 'demande', 'pour', 'avec', 'dans', 'faire'}]
        service_filter = Q()
        for term in terms:
            service_filter |= Q(service_name__icontains=term) | Q(service_code__icontains=term)
        matched_services = list(OfficialServiceRegistry.objects.filter(service_filter, is_active=True)[:2]) if terms else []
        for service in matched_services:
            snapshot = get_official_snapshot(service) if search_web else get_official_snapshot(service, allow_network=False)
            passages = snapshot_source_passages(snapshot, limit=16000)
            context_chunks.append(json.dumps({
                'service': service.service_name, 'institution': service.institution,
                'source_url': service.official_portal_url, 'source_checked_at': snapshot.get('checked_at'),
                'source_available': snapshot.get('available', False), 'supported_facts': snapshot.get('facts', {}),
                'source_text_excerpt': (snapshot.get('text') or '')[:16000] if snapshot.get('available') else '',
                'instruction': 'Use only these source-supported facts for fees, documents, deadlines and procedure. '
                               'Follow the published steps in order. Missing information is unknown; do not fill gaps '
                               'from memory, seed data or assumptions. Cite the page URL for each factual claim.',
            }, ensure_ascii=False))
            urls = {service.official_portal_url} if service.official_portal_url else set()
            for value in snapshot.get('facts', {}).values():
                for fact in value if isinstance(value, list) else [value]:
                    if isinstance(fact, dict) and fact.get('url'):
                        urls.add(fact['url'])
            for url in urls:
                sources.append({'institution': service.institution, 'title': service.service_name,
                                'url': url, 'verified_at': snapshot.get('checked_at', '')[:10],
                                'excerpt': source_excerpt(passages.get(url, '')), '_content': passages.get(url, ''),
                                'excerpt_label': 'Extrait de la page'})
        # 2. Check Verified Official News (Current events, Security in the East, Government briefings)
        from apps.rag_engine.models import OfficialNews
        news_q = Q()
        q_lower = query.lower()
        
        east_keywords = [
            'kivu', 'goma', 'sake', 'ituri', 'securite', 'sécurité', 'masisi', 'fardc', 'm23',
            'luanda', 'vita', 'bienye bina endeleya'
        ]
        is_news_or_east_query = any(re.search(r'(?<!\w)' + re.escape(k) + r'(?!\w)', q_lower)
                                    for k in east_keywords)
        is_news_or_east_query |= bool(re.search(r"(?:à|a|dans)\s+l['’]est\b|\best\s+(?:de|du|congolais)\b", q_lower))
        
        if is_news_or_east_query:
            news_q |= Q(category='securite') | Q(region__icontains='Est') | Q(region__icontains='Nord-Kivu') | Q(region__icontains='Ituri')

        stopwords = {'les', 'des', 'une', 'aux', 'sur', 'par', 'est', 'avec', 'dans', 'pour', 'contre', 'quel', 'quels', 'quelle', 'quelles',
                     'comment', 'combien', 'cette', 'cela', 'plus', 'sont', 'etre', 'être',
                     'actualité', 'actualite', 'actualités', 'actualites', 'dernière', 'derniere',
                     'dernières', 'dernieres', 'nouvelle', 'nouvelles', 'news', 'latest', 'information',
                     'informations', 'fait', 'faire', 'tout', 'tous', 'nous', 'vous', 'leur', 'leurs',
                     'rdc', 'congo', 'congolaises', 'congolaise', 'congolais', 'pays',
                     'the', 'and', 'for', 'what', 'about', 'from'}
        query_words = [w for w in re.findall(r"\w+", q_lower) if len(w) >= 3 and w not in stopwords]
        for w in query_words:
            news_q |= Q(title__icontains=w) | Q(summary__icontains=w) | Q(region__icontains=w)

        matched_news = []
        if is_news_or_east_query or query_words or explicit_news_request:
            from datetime import timedelta
            from django.db.models import Case, When, Value, IntegerField
            relevance = Value(0, output_field=IntegerField())
            for word in query_words:
                relevance = relevance + Case(When(title__icontains=word, then=Value(3)),
                    When(summary__icontains=word, then=Value(1)), default=Value(0), output_field=IntegerField())
            candidates = list(OfficialNews.objects.approved().filter(news_q, is_verified=True,
                published_at__lte=timezone.now()).annotate(topic_score=relevance).order_by('-topic_score', '-published_at')[:30])
            if candidates and candidates[0].topic_score >= 6:
                best_score = candidates[0].topic_score
                candidates = [n for n in candidates if n.topic_score >= max(3, best_score // 2)]
            # Prefer photographs among comparably fresh reports, never revive old news for a picture.
            recent_candidates = [n for n in candidates if n.published_at >= timezone.now() - timedelta(days=7)]
            pool = recent_candidates or candidates
            matched_news = sorted(pool, key=lambda n: (n.published_at, n.topic_score, bool(n.image_url)), reverse=True)[:3]
            for n in matched_news:
                news_content = (
                    f"[ARTICLE ENREGISTRÉ: {n.title}]\n"
                    f"Catégorie: {n.get_category_display()}\n"
                    f"Région: {n.region}\n"
                    f"Date: {n.published_at.strftime('%d/%m/%Y à %H:%M')}\n"
                    f"Source: {n.source_name}\n"
                    f"Résumé: {n.summary}\n"
                    f"Développements: {n.full_content}\n"
                    f"URL EXACTE DE LA SOURCE: {n.source_url}\n"
                )
                context_chunks.append(news_content)
                if not any(src.get("url") == n.source_url for src in sources):
                    sources.append({
                        "institution": n.source_name,
                        "title": n.title,
                        "url": n.source_url,
                        "image_url": n.image_url or '',
                        "source_kind": "news",
                        "region": n.region or '',
                        "excerpt": source_excerpt(n.summary or n.full_content),
                        "_content": n.full_content or n.summary or '',
                        "excerpt_label": "Résumé enregistré",
                        "published_at": n.published_at.isoformat(),
                        "verified_at": ""
                    })

        # 3. Check Verified Official DRC Portals Registry (the 30 verified official government portals)
        from apps.rag_engine.official_portals import find_matching_official_portals
        matched_portals = find_matching_official_portals(query, max_results=2)
        for p in matched_portals:
            p_content = (
                f"[PORTAIL GOUVERNEMENTAL OFFICIEL VÉRIFIÉ: {p['name']}]\n"
                f"Catégorie: {p['category']}\n"
                f"Missions & Attributions: {p['description']}\n"
                f"URL EXACTE DU SITE OFFICIEL: {p['url']}\n"
                "Type: annuaire institutionnel uniquement. Ne prouve aucune actualité, loi nouvelle ou annonce."
            )
            context_chunks.append(p_content)
            # Avoid duplicate URLs in sources
            if not any(src.get("url") == p["url"] for src in sources):
                sources.append({
                    "institution": p["name"],
                    "title": f"Portail officiel {p['name']}",
                    "url": p["url"],
                    "verified_at": "",
                    "source_kind": "directory",
                    "_content": p['description']
                })

        # 3. Vector search on DocumentChunk if pgvector is available
        has_chunks = DocumentChunk.objects.exists()
        # This path filters stored chunks by text. Avoid downloading an embedding
        # model when the routing decision explicitly keeps research offline.
        query_vector = (self.generate_query_embedding(query) if search_web else True) if has_chunks else None
        if query_vector:
            try:
                relevant = Q()
                for word in query_words:
                    relevant |= Q(content__icontains=word) | Q(knowledge_base__title__icontains=word)
                chunks = DocumentChunk.objects.select_related('knowledge_base').filter(relevant)[:top_k] if query_words else []
                for chk in chunks:
                    exact_url = chk.knowledge_base.original_url
                    if not exact_url:
                        continue
                    context_chunks.append(
                        f"[EXTRAIT OFFICIEL - {chk.knowledge_base.institution}]\n"
                        f"Titre: {chk.knowledge_base.title}\n"
                        f"Contenu: {chk.content}\n"
                        f"URL EXACTE DU SITE OFFICIEL: {exact_url}\n"
                        f"Date de vérification: {chk.knowledge_base.verified_at.strftime('%d/%m/%Y')}"
                    )
                    if not any(src.get("url") == exact_url for src in sources):
                        sources.append({
                            "institution": chk.knowledge_base.institution,
                            "title": chk.knowledge_base.title,
                            "url": exact_url,
                            "excerpt": source_excerpt(chk.content),
                            "_content": chk.content,
                            "excerpt_label": "Extrait du document",
                            "verified_at": chk.knowledge_base.verified_at.strftime("%d/%m/%Y")
                        })
            except Exception as e:
                logger.warning(f"Vector search failed, falling back: {e}")

        if not search_web:
            return {'context_text': '\n\n'.join(context_chunks) if context_chunks else 'Aucun document interne trouvé.',
                    'sources': sources, 'fallback_used': False, 'has_context': bool(context_chunks),
                    'web_search_performed': False}

        # 4. Research the question from several independent perspectives.
        fallback_used = False
        logger.info(f"Invoking enhanced web browsing for query: '{query}'")
        search_tool = TavilyDRCSearchTool(max_results=5)
        include_social = explicit_news_request or bool(matched_news and matched_news[0].topic_score >= 6)
        social_results = []
        from .research_plan import merge_web_results, research_queries, search_perspectives
        social_search = None
        if include_social:
            from .social_research import search_live_x, stored_x_sources
            try:
                social_results = stored_x_sources(query_words)
            except Exception:
                logger.warning('Publications X enregistrées temporairement indisponibles', exc_info=True)
            social_search = lambda: search_live_x(query)
        search_results, live_social = search_perspectives(search_tool, research_queries(query), social_search)
        social_results.extend(live_social)
        if include_social:
            social_urls = set()
            for post in social_results:
                url = post.get('url', '')
                if not url or url in social_urls or any(source.get('url') == url for source in sources):
                    continue
                social_urls.add(url)
                context_chunks.append(
                    f"[PUBLICATION X NON VÉRIFIÉE : {post['institution']}]\n"
                    f"URL exacte : {url}\n"
                    f"Date de publication : {post.get('published_at') or 'inconnue'}\n"
                    f"Date de découverte : {post.get('retrieved_at') or 'inconnue'}\n"
                    f"Texte de la publication ou extrait indexé : {post.get('text', '')}\n"
                    "Attribuer ces propos au compte, sans les présenter comme des faits confirmés.")
                sources.append({**post, '_content': post.get('text', '')})
        web_results = merge_web_results(search_results)
        if web_results:
            web_entries = []
            for r in generation_sources(web_results):
                title = r.get("title", "Portail Officiel")
                url   = r.get("url", "")
                from urllib.parse import urlsplit
                host = (urlsplit(url).hostname or '').lower().removeprefix('www.')
                if host in ('x.com', 'twitter.com', 'mobile.x.com', 'mobile.twitter.com'):
                    # X posts use the account-checked path above, never generic page images.
                    continue
                snippet = r.get("snippet", "")
                page_text = r.get("raw_content", "")
                if title and url and (snippet or page_text):
                    web_entries.append(
                        f"[RÉSULTAT WEB À VÉRIFIER: {title}]\n"
                        f"Source URL: {url}\n"
                        f"Date de publication: {r.get('published_at') or 'inconnue'}\n"
                        f"Photo de cet article disponible : {'oui' if r.get('image_url') else 'non'}\n"
                        f"Date de consultation: {r.get('retrieved_at') or timezone.now().isoformat()}\n"
                        f"Extrait de la source: {snippet}\n"
                        f"Contenu de la page récupérée (peut être partiel): {page_text[:1400]}"
                    )
                    if not any(src.get("url") == url for src in sources):
                        sources.append({
                            "institution": title[:60],
                            "title": title,
                            "url": url,
                            "image_url": r.get('image_url', ''),
                            "excerpt": source_excerpt(snippet or page_text),
                            "_content": page_text or snippet,
                            "excerpt_label": "Extrait retrouvé sur le web",
                            "published_at": r.get('published_at', ''),
                            "retrieved_at": r.get('retrieved_at') or timezone.now().isoformat(),
                            "verified_at": ""
                        })
            if web_entries:
                fallback_used = True
                context_chunks.append("\n\n".join(web_entries))
        if not fallback_used:
            context_chunks.append('Recherche web : aucun résultat exploitable disponible ; ne prétends pas avoir vérifié le web.')
        elif any(result.get('status') == 'error' or not result.get('status') for result in search_results):
            context_chunks.append('Recherche web : certaines recherches ont échoué ; ne prétends pas à une vérification exhaustive.')

        return {
            "context_text": "\n\n".join(context_chunks) if context_chunks else "Aucun document interne trouvé.",
            "sources": sources,
            "fallback_used": fallback_used,
            "has_context": bool(context_chunks),
            "web_search_performed": True,
        }

    def validate_retrieval(self, question, retrieval):
        from .source_validation import validate_sources, reviewed_context
        sources = validate_sources(question, retrieval.get('sources', []), self.llm)
        context = reviewed_context(sources)
        if retrieval.get('web_search_performed') is False:
            context += '\nAucune recherche Internet en direct pour cette question ; les sources sont enregistrées ou en cache. Ne prétends pas les avoir vérifiées en direct.'
        return {**retrieval, 'sources': sources, 'context_text': context,
                'has_context': bool(sources)}

    def conversation_history(self, session_id):
        if not session_id:
            return []
        try:
            from .chroma_session_manager import ChromaSessionManager
            return ChromaSessionManager().get_session_history(session_id)
        except Exception:
            logger.warning('Conversation history unavailable')
            return []

    def build_prompt_messages(self, query: str, context: str, user_language: str = "fr",
                              sources: Optional[List[Dict]] = None, history=None) -> List[Any]:
        """Constructs LangChain messages with system instructions, verified context, exact source URLs, and strict language enforcement."""
        sources = generation_sources(sources)
        from .news_answers import NEWS_SYSTEM_PROMPT, news_question
        answer_instructions = NEWS_SYSTEM_PROMPT if news_question(query) else DRC_GOV_SYSTEM_PROMPT
        illustrated = [source for source in sources if source.get('image_url') and source.get('source_kind') != 'directory'][:3]
        writing_plan = '\nPRIORITÉ DE RÉDACTION POUR LES ACTUALITÉS :\n'
        writing_plan += 'Privilégie les sources pertinentes les plus récentes ; considère les articles illustrés suivants si leur contenu est pertinent. '
        writing_plan += 'Pour chacun utilisé, expose le fait étayé avec sa date et cite son URL dans le même paragraphe. '
        writing_plan += 'Ces citations déclenchent les photos dans le corps de la réponse. Ne te contente pas de les lister en fin de réponse. '
        writing_plan += 'Écarte tout article hors sujet ou dépassé par une source plus récente ; la photo ne justifie jamais un fait non étayé.\n'
        for source in illustrated:
            writing_plan += f"- {source.get('title', '')} | publication : {source.get('published_at') or 'inconnue'} | {source.get('url', '')}\n"
        if user_language == "ln":
            lang_directive = (
                "=====================================================\n"
                "AGIZO YA MOTUYA — LOKOTA : LINGÁLA (OBLIGATOIRE)\n"
                "=====================================================\n"
                "Olingi koyanola OBLIGATOIREMENT NA LINGÁLA.\n"
                "Titre, mituna, batoli, malako nyonso ya Leta, na ba explications esengeli kozala na Lingála.\n"
                "Kokanisa te na lifalanse (français). Yanola mobimba na Lingála ya pete mpe ya lokumu.\n"
                "Salela batitre ya Markdown na Lingála (ndakisa: '## Ndima na ndenge ya kosala', '### Misala ya Leta', '### Mikanda esengeli', '### Mbongo ya kofuta', '### Ntango mpe bisika', '### Site officiel').\n"
                "IMPORTANT : Même si les documents ci-dessous sont en français, TRADUIS TOUT EN LINGÁLA pour le citoyen."
            )
        elif user_language == "sw":
            lang_directive = (
                "=====================================================\n"
                "AGIZO LA LAZIMA — LUGHA : KISWAHILI (DRC) (OBLIGATOIRE)\n"
                "=====================================================\n"
                "LAZIMA UJIBU KWA KISWAHILI SANIFU CHA JAMHURI YA KIDEMOKRASIA YA KONGO.\n"
                "Majibu yote lazima yaandikwe kwa Kiswahili safi, chenye heshima na ukweli kamili.\n"
                "Usijibu kwa Kifaransa. Jibu lote liwe kwa Kiswahili.\n"
                "- Ikiwa ni swali la utaratibu wa serikali (mfano pasipoti, kitambulisho, visa): tumia '## Utaratibu', '### Hati Zinazohitajika', '### Ada Rasmi', '### Tovuti Rasmi'.\n"
                "- Ikiwa ni swali la habari za nchi, usalama au hali ya mashariki (kama 'bienye bina endeleya ku est', 'hali ya Goma'): tumia '## Hali ya Usalama Mashariki', '### Matukio ya Hivi Karibuni', '### Taarifa za FARDC na Serikali', '### Vyanzo Rasmi'. USITUMIE muundo wa ada wala ofisi ya GUCE kwa habari za vita na usalama !\n"
                "MUHIMU : Hata kama nyaraka zilizo hapa chini ziko kwa Kifaransa, jibu swali tu kwa Kiswahili; usitafsiri nyaraka zote."
            )
        else:
            lang_directive = (
                "=====================================================\n"
                "DIRECTIVE DE LANGUE : FRANÇAIS OFFICIEL (OBLIGATOIRE)\n"
                "=====================================================\n"
                "Rédige l'intégralité de ta réponse en français soigné, clair et accessible à tous les citoyens."
            )

        # Build an explicit sources table so the model can copy exact URLs
        sources_block = ""
        if sources:
            sources_block = "\n\n=== URLS EXACTES DES SOURCES — À UTILISER TELLES QUELLES DANS LA RÉPONSE ===\n"
            for i, s in enumerate(sources, 1):
                url = s.get("url", "")
                if url and url not in ("Guichet officiel", "Dépôt physique"):
                    sources_block += (
                        f"[SOURCE {i}]\n"
                        f"  Institution : {s.get('institution', '')}\n"
                        f"  Titre       : {s.get('title', '')}\n"
                        f"  URL EXACTE  : {url}\n"
                        f"  Passage disponible : {s.get('excerpt') or 'aucun texte disponible'}\n"
                        f"  Publication : {s.get('published_at') or 'date inconnue'}\n"
                        f"  Consultation : {s.get('retrieved_at') or s.get('verified_at') or 'non précisée'}\n"
                        f"  Image disponible : {'oui' if s.get('image_url') else 'non'}\n"
                    )
            sources_block += "==========================================================================="

        system_content = (
            f"Date actuelle en RDC : {timezone.localdate().isoformat()}.\n"
            f"{lang_directive}\n\n"
            f"{answer_instructions}\n\n"
            f"{DRC_SCOPE_INSTRUCTIONS}\n\n"
            f"{writing_plan}\n"
            f"=== DOCUMENTS ET SOURCES FOURNIS (statut et attribution précisés) ===\n"
            f"{context}\n"
            f"=================================================={sources_block}\n\n"
            f"{lang_directive}"
            '\nCITATION RULES: Use only exact URLs supplied in the source table. Never invent a path, date, '
            'article title or verification date. Cite the specific publication beside each factual news claim. '
            'A ministry homepage or directory description establishes identity only, never recent events, '
            'new laws, inspections or programmes. Do not infer news from institutional mandates. '
            'If no relevant publication supports a claim, omit it and clearly say the requested news could not be confirmed. '
            'Use publication dates as publication dates, never as dates of verification. '
            'For general factual questions, answer the actual question directly using the supplied web pages, '
            'For questions asking why, implications, recommendations or an opinion, go beyond a summary: '
            'offer a reasoned assessment that follows from the evidence, explain the reasoning and trade-offs, '
            'and fairly address meaningful alternative interpretations. Clearly distinguish analysis or '
            'judgment from sourced facts, acknowledge uncertainty, and never invent evidence or personal experience. '
            'Match the depth to the question rather than forcing every answer into a short news briefing. '
            'Alongside the answer and any needed analysis, give a separate concise one- or two-sentence briefing for each relevant source with readable content, '
            'explaining what it reports and how it relates to the question. Name it and cite its exact URL and date when known. '
            'Do not merely list links or invent facts to fill an overview; say when a source has no readable content. '
            'including reputable independent media and documented reports. Do not require a government-only source. '
            'Attribute media reporting explicitly; do not call it officially verified. '
            'For salaries, give supported amounts, currency, rank/category and date; distinguish salary, allowances, '
            'announced increases and actual payments. Reconcile differing dated reports instead of choosing blindly. '
            'Only use the administrative procedure template and anti-fraud payment warning for an actual application '
            'or payment procedure, never for a general question such as how much soldiers earn. '
            'Do not send the user to contact a ministry when the retrieved pages already answer the question. '
            'Never say a page may contain the answer: report what its supplied text actually states. '
            'The interface automatically places available article photographs next to their exact citations. '
            'Do not ask whether the user wants pictures, do not promise unavailable photographs, and do not invent image URLs. '
            'Cite the relevant article naturally beside the passage it supports so its photograph can appear in context. '
            'When discussing multiple news stories, write a separate paragraph or numbered list item for each story. '
            'Put the exact source URL inside that story’s own paragraph or list item, before starting the next story. '
            'Never attach an image or citation from a different story merely to illustrate text. '
            'Public X posts are unverified statements: attribute them to their account, distinguish them from '
            'independent reporting, and do not mistake discovery time for the publication date. '
            'Prefer relevant illustrated articles when they are comparably recent, but never sacrifice factual relevance '
            'or use an older event as current just to display an image. Distinguish publication date, event date and retrieval date. '
            'State dates for changing facts and recent developments. An undated page is not evidence of today’s situation. '
            'Prioritize the newest relevant and supported information, cross-check sources and distinguish '
            'recent updates from older background. Historical questions can require older primary sources. '
            'Do not present a future-dated report or event as something that has already occurred. '
            'When only older sources are available, identify their dates and explicitly say current status is unconfirmed. '
            'The application retrieves sources before generation. Answer from the supplied passages; '
            'do not replace a supported answer with a generic claim that an AI cannot access recent news. '
            'If no relevant passages are supplied, describe this search limitation accurately. '
        )

        from .conversation_history import model_history
        messages = [SystemMessage(content=system_content + '\nUse the preceding user and assistant turns '
            'to understand follow-up questions and details already supplied. Conversation history is '
            'not an official source: correct earlier mistakes using the supplied evidence.')]
        for turn in model_history(history or []):
            message_type = HumanMessage if turn['role'] == 'user' else AIMessage
            messages.append(message_type(content=turn['content']))
        messages.append(HumanMessage(content=query))
        return messages

    def response_model(self, user_language):
        if user_language == 'ln' and getattr(settings, 'OLLAMA_LINGALA_MODEL', ''):
            return get_chat_ollama('ln')
        return self.llm

    def answer_query(self, query: str, user_language: str = "fr", session_id=None,
                     web_search=None, context_only=None) -> Dict[str, Any]:
        """
        Executes a complete RAG query synchronously.
        Logs to QueryAuditLog for auditability and compliance.
        """
        start_time = datetime.now()
        from .conversation_history import retrieval_question
        history = self.conversation_history(session_id)
        from .langgraph_router import classify_query_intent, web_search_node
        decision = web_search_node({'query': query, 'history': history})
        if web_search is not None:
            decision['web_search'] = bool(web_search)
        if context_only is not None:
            decision['context_only'] = bool(context_only)
        direct_answer = classify_query_intent(query, user_language) == 'casual' or decision['context_only']
        if direct_answer:
            from .conversation import conversation_messages
            retrieval = {'context_text': '', 'sources': [], 'fallback_used': False}
            messages = conversation_messages(query, user_language, history)
        else:
            search_query = retrieval_question(query, history)
            candidates = self.retrieve_context(search_query) if decision['web_search'] else self.retrieve_context(search_query, search_web=False)
            retrieval = self.validate_retrieval(search_query, candidates)
            messages = self.build_prompt_messages(query, retrieval["context_text"], user_language,
                                                  sources=retrieval["sources"], history=history)

        try:
            response = self.response_model(user_language).invoke(messages)
            if direct_answer:
                answer_text = response.content
            else:
                from types import SimpleNamespace
                resolved = ''.join(chunk.content for chunk in numbered_citation_chunks(
                    [SimpleNamespace(content=response.content)], generation_sources(retrieval['sources'])))
                answer_text = validate_citation_paragraphs(resolved, retrieval['sources'])

            from .source_validation import public_sources
            retrieval['sources'] = public_sources(cited_sources(answer_text, retrieval['sources']))

            elapsed_ms = int((datetime.now() - start_time).total_seconds() * 1000)

            # Record audit log
            QueryAuditLog.objects.create(
                query_text=query,
                detected_language=user_language,
                response_text=answer_text,
                sources_cited=retrieval["sources"],
                tool_fallback_used=retrieval["fallback_used"],
                execution_time_ms=elapsed_ms
            )

            return {
                "status": "success",
                "query": query,
                "answer": answer_text,
                "sources": retrieval["sources"],
                "fallback_used": retrieval["fallback_used"],
                "execution_time_ms": elapsed_ms
            }

        except Exception as e:
            logger.error(f"Error in DRCRagService.answer_query: {e}")
            return {
                "status": "error",
                "query": query,
                "answer": (
                    "Désolé, le service d'assistance gouvernementale rencontre actuellement "
                    "une indisponibilité technique temporaire. Veuillez réessayer dans quelques instants "
                    "ou vous rapprocher du bureau d'information ministériel."
                ),
                "error": str(e),
                "sources": []
            }

    def stream_query(self, query: str, user_language: str = "fr", session_id=None) -> Generator[str, None, None]:
        """
        Streams response tokens in real-time for SSE / WebSockets.
        """
        from .conversation_history import retrieval_question
        from .langgraph_router import classify_query_intent, web_search_node
        history = self.conversation_history(session_id)
        decision = web_search_node({'query': query, 'history': history})
        direct_answer = classify_query_intent(query, user_language) == 'casual' or decision['context_only']
        if direct_answer:
            from .conversation import conversation_messages
            retrieval = {'sources': []}
            messages = conversation_messages(query, user_language, history)
        else:
            search_query = retrieval_question(query, history)
            candidates = self.retrieve_context(search_query) if decision['web_search'] else self.retrieve_context(search_query, search_web=False)
            retrieval = self.validate_retrieval(search_query, candidates)
            messages = self.build_prompt_messages(query, retrieval["context_text"], user_language,
                                                  sources=retrieval["sources"], history=history)

        try:
            chunks = bounded_chunks(self.response_model(user_language).stream(messages))
            if not direct_answer:
                chunks = numbered_citation_chunks(chunks, generation_sources(retrieval['sources']))
                chunks = citation_chunks(chunks, retrieval['sources'])
            for chunk in chunks:
                yield chunk.content
        except Exception as e:
            logger.error(f"Error during streaming: {e}")
            yield f"\n\n[Erreur technique: {str(e)}]"

    def stream_query_events(self, query: str, user_language: str = "fr", session_id: Optional[str] = None, history=None):
        """
        Structured streaming generator yielding JSON-compatible events:
        - {"type": "sources", "sources": [...], "fallback_used": bool}
        - {"type": "token", "token": "..."}
        - {"type": "done", "session_id": "...", "full_answer": "..."}
        
        Uses the intent classifier to skip document retrieval for small talk.
        Both conversational and researched answers stream directly from the model.
        """
        from apps.rag_engine.langgraph_router import classify_query_intent, web_search_node
        from .conversation_history import retrieval_question
        from .conversation_history import read_history
        history = read_history(history) if history is not None else self.conversation_history(session_id)
        intent = classify_query_intent(query, user_language)
        decision = web_search_node({'query': query, 'history': history})
        direct_answer = intent == 'casual' or decision['context_only']
        
        if direct_answer:
            from .conversation import conversation_messages
            retrieval = {'context_text': '', 'sources': [], 'fallback_used': False}
            messages = conversation_messages(query, user_language, history)
        else:
            search_query = retrieval_question(query, history)
            yield {'type': 'status', 'message': 'Recherche sur Internet…' if decision['web_search'] else 'Consultation des informations enregistrées…'}
            candidates = self.retrieve_context(search_query) if decision['web_search'] else self.retrieve_context(search_query, search_web=False)
            yield {'type': 'status', 'message': 'Vérification de la pertinence des sources…'}
            retrieval = self.validate_retrieval(search_query, candidates)
            messages = self.build_prompt_messages(query, retrieval['context_text'], user_language,
                                                 sources=retrieval['sources'], history=history)

        from .source_validation import public_sources
        yield {
            "type": "sources",
            "sources": [{**source, 'reference_only': True} for source in public_sources(retrieval["sources"])],
            "fallback_used": retrieval["fallback_used"],
            "classification": intent,
            "web_search_performed": bool(not direct_answer and decision['web_search'])
        }

        accumulated_tokens = []
        try:
            chunks = bounded_chunks(self.response_model(user_language).stream(messages))
            if not direct_answer:
                chunks = numbered_citation_chunks(chunks, generation_sources(retrieval['sources']))
                chunks = citation_chunks(chunks, retrieval['sources'])
            for chunk in chunks:
                token = chunk.content
                if token:
                    accumulated_tokens.append(token)
                    yield {
                        "type": "token",
                        "token": token
                    }
        except Exception as e:
            logger.error(f"Error during streaming: {e}")
            yield {
                "type": "token",
                "token": f"\n\n[Indisponibilité technique: {str(e)}]"
            }

        full_answer = "".join(accumulated_tokens)
        retrieval['sources'] = public_sources(answer_references(full_answer, retrieval['sources']))

        # Save turn to ChromaDB vector store
        history_saved = None
        if session_id:
            try:
                from apps.rag_engine.chroma_session_manager import ChromaSessionManager
                cm = ChromaSessionManager()
                user_saved = cm.save_message(session_id, role="user", content=query)
                ai_saved = cm.save_message(session_id, role="assistant", content=full_answer, sources=retrieval["sources"])
                history_saved = bool(user_saved and ai_saved)
            except Exception as e:
                history_saved = False
                logger.error(f"Error writing to ChromaDB: {e}")

        yield {
            "type": "done",
            "session_id": session_id,
            "full_answer": full_answer,
            "history_saved": history_saved,
            "sources": retrieval["sources"]
        }

