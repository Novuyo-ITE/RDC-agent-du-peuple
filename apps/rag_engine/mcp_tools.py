"""
MCP (Model Context Protocol) and Web Search Tools for DRC Government Digital Assistant.
Integrates:
1. Tavily: Real-time search for public news, official communiqués, and ministries.
2. OfficialServiceDirectoryTool: Direct grounded queries to the OfficialServiceRegistry.
3. MCPToolBridge: Standardized adapter for Model Context Protocol (MCP) server endpoints.
4. Source Verification Formatter: Enforcing FRD v1.1 mandatory citation structure.
"""

import json
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime

from langchain_core.tools import tool, BaseTool
from apps.rag_engine.web_search import TavilyDRCSearchTool

logger = logging.getLogger(__name__)


import re
import urllib.request
from bs4 import BeautifulSoup


def clean_web_snippet(text: str) -> str:
    """Strips WordPress shortcodes, base64 blobs, CSS blocks, and corrupted tokens."""
    if not text:
        return ""
    # Strip WordPress shortcodes like [vc_...], [tdc_...], [tdm_...]
    t = re.sub(r'\[/?(?:vc_|tdc_|tdm_|fusion_|elementor_|et_pb_|caption)[^\]]*\]', ' ', text)
    # Strip base64 blocks like JTNDYn...
    t = re.sub(r'[A-Za-z0-9+/=]{40,}', ' ', t)
    # Strip CSS styles or code fragments
    t = re.sub(r'\{[^\}]*\}', ' ', t)
    # Normalize whitespace
    t = re.sub(r'\s+', ' ', t).strip()
    return t


def fetch_clean_page_content(url: str, timeout: int = 3) -> str:
    """Fetches and cleans main text content from a web page to provide deep grounded knowledge."""
    if not url or not url.startswith(('http://', 'https://')):
        return ""
    try:
        req = urllib.request.Request(
            url,
            headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            html = resp.read().decode('utf-8', errors='ignore')
            soup = BeautifulSoup(html, 'html.parser')
            for tag in soup(['script', 'style', 'nav', 'footer', 'header', 'noscript', 'meta', 'aside', 'svg']):
                tag.decompose()
            
            # Prioritize main article or body
            main_block = soup.find('main') or soup.find('article') or soup.find(class_='content') or soup.find('body')
            if main_block:
                text = ' '.join(main_block.stripped_strings)
            else:
                text = ' '.join(soup.stripped_strings)
            
            cleaned = clean_web_snippet(text)
            return cleaned[:800]  # Cap to 800 high-density chars
    except Exception as e:
        logger.debug(f"Could not scrape {url}: {e}")
        return ""


def format_mandatory_citation(source: str, verified_date: Optional[str] = None, official_url: Optional[str] = None) -> str:
    """
    Formats the mandatory FRD v1.1 citation block.
    Every administrative or news response must include this block.
    """
    date_display = verified_date or datetime.now().strftime("%d/%m/%Y")
    url_display = official_url or "http://presidentrdc.cd/"
    return (
        f"\n\n---\n"
        f"### Source officielle\n"
        f"- **Institution** : {source}\n"
        f"- **Lien officiel exact** : [{url_display}]({url_display})\n"
        f"- **Date de vérification** : {date_display}"
    )




@tool
def search_drc_web(query: str) -> str:
    """
    Recherche sur le web les informations officielles récentes sur la République Démocratique du Congo.
    À utiliser lorsque la base de connaissances interne ne contient pas d'information récente
    sur un arrêté, un décret, une actualité ou une annonce gouvernementale.
    """
    searcher = TavilyDRCSearchTool(max_results=3)
    res = searcher.search(query)
    if res.get("status") == "success":
        return f"Résultats de recherche en direct pour '{query}':\n{res['results_raw']}\nSource: {res['source']}"
    return f"Aucun résultat web probant trouvé pour: {query}."


@tool
def lookup_official_service(service_name_or_keyword: str) -> str:
    """
    Consulte le Registre Officiel des Services Publics de la RDC (Passeport, Acte de Naissance,
    Permis de Conduire, RCCM / GUCE, etc.) pour obtenir les frais officiels vérifiés,
    les pièces justificatives requises, les bureaux de dépôt et les délais légaux.
    Garantit zéro hallucination sur les démarches administratives.
    """
    from apps.rag_engine.models import OfficialServiceRegistry
    from django.db.models import Q

    try:
        services = OfficialServiceRegistry.objects.filter(
            Q(service_name__icontains=service_name_or_keyword) |
            Q(description__icontains=service_name_or_keyword) |
            Q(service_code__icontains=service_name_or_keyword) |
            Q(institution__icontains=service_name_or_keyword),
            is_active=True
        )[:3]

        if not services.exists():
            return (
                f"Aucune démarche officielle répertoriée ne correspond exactement à '{service_name_or_keyword}'. "
                "Pour éviter toute erreur ou intermédiaire frauduleux, veuillez orienter le citoyen "
                "vers le guichet de l'institution compétente ou consulter le répertoire officiel."
            )

        output_blocks = []
        for s in services:
            from apps.rag_engine.official_service_portal import get_official_snapshot
            snapshot = get_official_snapshot(s)
            block = json.dumps({
                'service': s.service_name, 'institution': s.institution,
                'source_url': s.official_portal_url, 'checked_at': snapshot.get('checked_at'),
                'source_available': snapshot.get('available', False),
                'supported_facts': snapshot.get('facts', {}),
                'instruction': 'Use only these source quotes for procedural facts; missing information is unknown.',
            }, ensure_ascii=False)
            output_blocks.append(block)

        return "\n\n".join(output_blocks)

    except Exception as e:
        logger.error(f"Error querying OfficialServiceRegistry: {e}")
        return f"Erreur lors de la consultation du registre des services: {str(e)}"


class MCPToolBridge:
    """
    Standardized adapter for Model Context Protocol (MCP) server endpoints.
    Allows dynamic registration and execution of external MCP tools (stdio / sse)
    for DRC government integration (e.g. Journal Officiel digital archives, cadastre).
    """
    def __init__(self, server_name: str = "drc_gov_mcp_gateway"):
        self.server_name = server_name
        self.registered_tools: Dict[str, Any] = {}

    def register_tool(self, name: str, description: str, handler_callable):
        """Registers an MCP callable tool with JSON schema metadata."""
        self.registered_tools[name] = {
            "name": name,
            "description": description,
            "handler": handler_callable
        }
        logger.info(f"Registered MCP tool '{name}' on bridge '{self.server_name}'")

    def execute_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Executes a registered MCP tool following the MCP protocol specification."""
        if tool_name not in self.registered_tools:
            return {
                "error": f"Tool '{tool_name}' not found on MCP bridge '{self.server_name}'",
                "is_error": True
            }
        try:
            handler = self.registered_tools[tool_name]["handler"]
            result = handler(**arguments)
            return {
                "content": [{"type": "text", "text": str(result)}],
                "is_error": False
            }
        except Exception as err:
            logger.error(f"MCP tool execution failed ({tool_name}): {err}")
            return {
                "content": [{"type": "text", "text": f"Error: {str(err)}"}],
                "is_error": True
            }

    def list_tools(self) -> List[Dict[str, str]]:
        """Returns metadata for all available MCP tools."""
        return [
            {"name": t["name"], "description": t["description"]}
            for t in self.registered_tools.values()
        ]


# Default tool bindings for LangChain Agent
RAG_AGENT_TOOLS: List[BaseTool] = [
    lookup_official_service,
    search_drc_web
]

