"""
LangGraph Query Classifier & Routing Engine for DRC Government Digital Assistant.
Uses StateGraph to classify whether a citizen query is:
1. "casual" (Greetings, pleasantries, small talk) -> Fast direct response, avoiding heavy RAG/tool latency.
2. "research_needed" (Official procedures, legal decrees, tariffs, civil status, ministries) -> Full grounded RAG retrieval pipeline.
"""

import re
import logging
import unicodedata
from typing import TypedDict, List, Dict, Any, Optional

from langgraph.graph import StateGraph, END
from langchain_core.messages import SystemMessage, HumanMessage

logger = logging.getLogger(__name__)

# Fast recognition patterns for casual greetings across French, Lingala, and Swahili
CASUAL_PATTERNS = [
    r'^(bonjour|salut|bonsoir|coucou|hello|hi|hey)\b',
    r'^(mbote|mbote na yo|mbote na bino|sango nini)\b',
    r'^(jambo|habari|habari gani|hujambo|salama)\b',
    r'^(merci|merci beaucoup|matondi|asante|asante sana)\b',
    r'^(qui es[- ]tu|tu es qui|comment tu t\'appelles|kombo na yo nani)\b',
    r'^(comment (vas[- ]tu|allez[- ]vous)|ça va|ozali malamu)\b',
    r'^(au revoir|tokomonana|kwaheri|bonne journée|bonne nuit)\b'
]
CASUAL_REGEX = re.compile('|'.join(CASUAL_PATTERNS), re.IGNORECASE)


class GraphState(TypedDict):
    query: str
    user_language: str
    session_id: Optional[str]
    classification: str  # "casual" or "research_needed"
    context_text: str
    sources: List[Dict[str, Any]]
    fallback_used: bool
    answer: str
    history: List[Dict[str, str]]
    web_search: bool
    context_only: bool
    web_reason: str


def _normalized(text):
    return ''.join(char for char in unicodedata.normalize('NFKD', text.lower())
                   if not unicodedata.combining(char)).replace('’', "'")


def web_search_node(state: GraphState) -> Dict[str, Any]:
    """Choose web research conservatively; preserve explicit user constraints."""
    from .conversation_history import retrieval_question

    query = state.get('query', '').strip()
    text = _normalized(query)
    history = state.get('history') or []
    kind = state.get('context_kind', 'main')
    no_web = re.search(
        r"\b(?:sans\s+(?:utiliser\s+|consulter\s+|faire\s+)?(?:de\s+|du\s+|le\s+)?(?:internet|web|recherche|rechercher|navigation)|"
        r"(?:ne\s+)?(?:cherche|recherche|navigue)\s+pas\b|"
        r"(?:do not|don't|dont)\s+(?:search|browse)\b|"
        r"n'?(?:utilise|utilisez)\s+pas\b.{0,35}\b(?:internet|web|ligne)|"
        r"(?:ne\s+)?(?:cherche|recherche|consulte|navigue|verifie)\s+pas\b.{0,40}\b(?:internet|web|ligne|source)|"
        r"(?:ne\s+)?(?:fais|va)\s+pas\b.{0,40}\b(?:internet|web|ligne|recherche)|"
        r"(?:pas\s+d'internet|without\s+internet|no\s+internet)|"
        r"(?:pas|aucune)\s+(?:de\s+)?recherch(?:e|er)\s+(?:sur\s+)?(?:internet|web|en ligne)|"
        r"(?:do not|don't|dont|without)\s+(?:search|browse|use|check)\b.{0,35}\b(?:internet|web|online)|"
        r"(?:no|without)\s+(?:web|internet|online)\s+(?:search|browsing))\b", text)
    explicit_web = re.search(
        r"\b(?:cherche|recherche|verifie|consulte|search|browse|look up)\b.{0,45}\b(?:internet|web|ligne|online|source|site|article|information)|"
        r"\b(?:sur|avec|using|on|from)\s+(?:internet|le web|web|twitter|tweeter|facebook|instagram)\b|"
        r"\b(?:sur x|en ligne|online sources|web search)\b", text)
    contextual = _normalized(retrieval_question(query, history))
    sensitive_pattern = (
        r"\b(?:actualites?|news|habari|sango|latest|recent|recents|recente|recentes|aujourd'hui|"
        r"actuel|actuelle|actuellement|now|today|this week|cette semaine|dernier|derniers|derniere|dernieres|"
        r"prix|cout|frais|tarif|salaire|solde|montant|taux|salary|price|cost|rate|"
        r"loi|lois|juridique|legal|legale|reglement|decret|law|legal|tax|impot|"
        r"medicament|medical|sante|traitement|dosage|symptome|health|medicine|medical|"
        r"passeport|passport|visa|permis|procedure|documents|demarche|election|"
        r"m23|fardc|ebola|epidemie)\b")
    current_or_sensitive = re.search(sensitive_pattern, contextual)
    current_in_query = re.search(sensitive_pattern, text)
    personal_memory = re.search(
        r"\b(?:comment\s+(?:je\s+m'appelle|m'appelle-je)|quel(?:le)?\s+est\s+mon\s+(?:nom|prenom)|"
        r"qu(?:e|')\s*(?:ai-je|est-ce que j'ai)\s+dit|souviens.toi\s+de\s+(?:mon|ma|mes)|"
        r"what(?:'s| is) my name|what did i (?:say|tell you)|my name is|mon (?:nom|prenom) est)\b", text)
    text_work = re.search(
        r"\b(?:reformule|reformuler|reecris|reecrire|corrige|corriger|traduis|traduire|"
        r"resumes?|resumer|resumez|summarize|summarise|rewrite|translate|proofread)\b"
        r".{0,70}\b(?:ce texte|cet extrait|cette phrase|ce message|cette reponse|"
        r"notre conversation|la conversation|ce que (?:j'ai|tu as) dit|"
        r"this text|this message|your (?:last )?answer|our conversation)\b", text)
    inline_text_work = bool(re.search(r"\b(?:reformule|reecris|corrige|traduis|translate|rewrite)\b.{0,80}:", text))
    simple_math = bool(re.fullmatch(r'[\d\s+*/().,%−×÷-]+\??', text) and re.search(r'\d', text))
    direct = bool(text_work or inline_text_work or simple_math or (personal_memory and not current_in_query))
    selected_resource_question = kind in ('article', 'service') and bool(
        re.search(r"\b(?:cet article|l'article|cette actualite|l'actualite|ce texte|cette publication|"
                  r"la publication|cette source|ce document|le document|cet extrait|this article|"
                  r"this document|this source|the article|this page|ce service|cette fiche)\b", text)
        or re.fullmatch(r"(?:resumes?|resumer|explique|summarize|explain|que faut.il retenir)[\s?.!]*", text))

    if no_web or state.get('internet_allowed') is False:
        return {'web_search': False, 'context_only': direct, 'web_reason': 'user_disabled'}
    if explicit_web:
        return {'web_search': True, 'context_only': False, 'web_reason': 'current_or_source_dependent'}
    if classify_query_intent(query, state.get('user_language', 'fr')) == 'casual':
        return {'web_search': False, 'context_only': True, 'web_reason': 'conversation_or_text'}
    if selected_resource_question:
        if current_or_sensitive or state.get('resource_available') is False:
            return {'web_search': True, 'context_only': False, 'web_reason': 'selected_resource_needs_research'}
        return {'web_search': False, 'context_only': False, 'web_reason': 'selected_resource'}
    if direct:
        return {'web_search': False, 'context_only': True, 'web_reason': 'conversation_or_text'}
    if current_or_sensitive:
        return {'web_search': True, 'context_only': False, 'web_reason': 'current_or_source_dependent'}
    # For ambiguous or factual requests, preserve research rather than guess.
    return {'web_search': True, 'context_only': False, 'web_reason': 'factual_or_uncertain'}


def classify_query_intent(query: str, user_language: str = "fr") -> str:
    """
    Determines if query requires government document research or is casual chit-chat.
    Uses regex rules + query length for instant sub-millisecond evaluation.
    """
    cleaned = query.strip()
    # Specific government keywords that always require research
    gov_keywords = [
        "passeport", "visa", "acte", "naissance", "mariage", "deces", "permis", "conduire",
        "dgm", "guce", "rccm", "impot", "dgi", "dgrad", "douane", "tarif", "cout", "frais",
        "prix", "decret", "arrete", "loi", "ministre", "ministere", "presidence", "ambassade",
        "kinshasa", "goma", "lubumbashi", "nationalite", "carte", "identite", "citoyen",
        "police", "tribunal", "notaire", "cadastre", "parcelle", "titre", "dossier", "demande", "conditions"
    ]
    query_lower = cleaned.lower()
    if any(k in query_lower for k in gov_keywords):
        return "research_needed"

    casual_match = CASUAL_REGEX.search(cleaned)
    if casual_match and len(cleaned.split()) <= 6:
        # A greeting followed by a factual question still needs research.
        remainder = cleaned[casual_match.end():].strip(' \t\r\n,.!?…')
        if not remainder or re.fullmatch(
            r'(?:beaucoup|na yo|na bino|sana|ça va|comment (?:vas[- ]tu|allez[- ]vous)|how are you)',
            remainder, re.IGNORECASE,
        ):
            return "casual"

    # Default to research to ensure accurate administrative assistance
    return "research_needed"


def classifier_node(state: GraphState) -> Dict[str, Any]:
    """Node that assigns the query classification."""
    intent = classify_query_intent(state["query"], state.get("user_language", "fr"))
    logger.info(f"LangGraph query classification for '{state['query'][:40]}...': {intent}")
    return {"classification": intent}


def casual_responder_node(state: GraphState) -> Dict[str, Any]:
    """
    Generates an immediate, friendly official greeting without spending time
    on heavy vector search or external scraping tools.
    """
    from .services import get_chat_ollama
    from .conversation import conversation_messages
    from .chroma_session_manager import ChromaSessionManager
    history = ChromaSessionManager().get_session_history(state['session_id']) if state.get('session_id') else []
    response = get_chat_ollama(state.get('user_language', 'fr')).invoke(conversation_messages(
        state['query'], state.get('user_language', 'fr'), history))
    return {'answer': response.content, 'sources': [], 'fallback_used': False}


def research_rag_node(state: GraphState) -> Dict[str, Any]:
    """
    Runs the full RAG service with vector retrieval, OfficialServiceRegistry checks,
    and step-by-step explanatory generation.
    """
    from apps.rag_engine.services import DRCRagService
    service = DRCRagService()
    result = service.answer_query(
        query=state["query"],
        user_language=state.get("user_language", "fr"), session_id=state.get('session_id'),
        web_search=state.get('web_search'), context_only=state.get('context_only')
    )
    return {
        "answer": result.get("answer", ""),
        "sources": result.get("sources", []),
        "fallback_used": result.get("fallback_used", False)
    }


def route_decision(state: GraphState) -> str:
    """Conditional edge router based on classification."""
    if state["classification"] == "casual":
        return "casual_responder"
    return "web_decision"


def graph_web_decision(state: GraphState) -> Dict[str, Any]:
    history = state.get('history')
    if history is None and state.get('session_id'):
        try:
            from .chroma_session_manager import ChromaSessionManager
            history = ChromaSessionManager().get_session_history(state['session_id'])
        except Exception:
            logger.warning('Conversation history unavailable for web routing.')
    return web_search_node({**state, 'history': history or []})


# Compile LangGraph StateGraph
builder = StateGraph(GraphState)
builder.add_node("classifier", classifier_node)
builder.add_node("web_decision", graph_web_decision)
builder.add_node("casual_responder", casual_responder_node)
builder.add_node("research_rag", research_rag_node)

builder.set_entry_point("classifier")
builder.add_conditional_edges(
    "classifier",
    route_decision,
    {
        "casual_responder": "casual_responder",
        "web_decision": "web_decision"
    }
)
builder.add_edge("casual_responder", END)
builder.add_edge("web_decision", "research_rag")
builder.add_edge("research_rag", END)

DRC_ROUTING_GRAPH = builder.compile()

