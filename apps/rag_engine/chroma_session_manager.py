"""
ChromaDB Session & Chat History Vector Storage for DRC Government Assistant.
Provides:
1. Persistent vector storage of chat sessions, messages, and conversation embeddings.
2. Session management: list, create, rename, delete with immediate metadata updates.
3. Historical context search across past consultations.
"""

import json
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime
from pathlib import Path
from uuid import uuid4
from django.conf import settings

import chromadb
from chromadb.config import Settings

logger = logging.getLogger(__name__)


def format_chat_title(title):
    title = (title or '').strip() or 'Consultation'
    return title[:1].upper() + title[1:]


def session_destination(session_id, metadata):
    from django.urls import reverse
    from urllib.parse import urlencode
    if metadata.get('kind') == 'article' and metadata.get('article_id'):
        return reverse('web_ui:news') + '?' + urlencode({'article': metadata['article_id'], 'session': session_id})
    if metadata.get('kind') == 'service' and metadata.get('service_code'):
        return reverse('web_ui:service_workspace', args=[metadata['service_code']]) + '?' + urlencode({'session': session_id})
    return reverse('web_ui:chat') + '?' + urlencode({'session': session_id})

_CHROMA_CLIENT = None


def get_chroma_client() -> chromadb.ClientAPI:
    """Singleton Chroma persistent client pointing to drc_gov_agent/chroma_db."""
    global _CHROMA_CLIENT
    if _CHROMA_CLIENT is None:
        chroma_dir = Path(settings.CHROMA_PERSIST_DIRECTORY)
        chroma_dir.mkdir(parents=True, exist_ok=True)
        _CHROMA_CLIENT = chromadb.PersistentClient(
            path=str(chroma_dir),
            settings=Settings(anonymized_telemetry=False)
        )
    return _CHROMA_CLIENT


class ChromaSessionManager:
    """Manages chat history and semantic indexing using ChromaDB."""

    def __init__(self):
        self.client = get_chroma_client()
        self.sessions_coll = self.client.get_or_create_collection(
            name="drc_chat_sessions",
            metadata={"description": "Metadata and summaries of DRC citizen chat sessions"}
        )
        self.messages_coll = self.client.get_or_create_collection(
            name="drc_chat_messages",
            metadata={"description": "Turn-by-turn messages with embeddings"}
        )

    def list_sessions(self) -> List[Dict[str, Any]]:
        """Returns all saved sessions sorted by last updated timestamp."""
        try:
            results = self.sessions_coll.get()
            sessions = []
            if results and results.get("ids"):
                for idx, session_id in enumerate(results["ids"]):
                    metadata = results["metadatas"][idx] if results.get("metadatas") else {}
                    sessions.append({
                        "id": session_id,
                        "title": format_chat_title(metadata.get("title", "Nouvelle consultation")),
                        "created_at": metadata.get("created_at", ""),
                        "updated_at": metadata.get("updated_at", ""),
                        "message_count": metadata.get("message_count", 0),
                        "kind": metadata.get('kind', 'chat'),
                        "article_id": metadata.get('article_id'),
                        "url": session_destination(session_id, metadata),
                    })

            # Sort newest first
            sessions.sort(key=lambda s: s.get("updated_at", ""), reverse=True)
            return sessions
        except Exception as e:
            logger.error(f"Error listing ChromaDB sessions: {e}")
            return []

    def get_session(self, session_id):
        result = self.sessions_coll.get(ids=[session_id])
        if result and result.get('ids'):
            meta = result['metadatas'][0]
            return {**meta, 'title': format_chat_title(meta.get('title')), 'id': session_id, 'url': session_destination(session_id, meta)}
        return None

    def get_or_create_session(self, session_id: str, title: Optional[str] = None, context=None) -> Dict[str, Any]:
        """Creates or retrieves a chat session entry."""
        now_iso = datetime.now().isoformat()
        try:
            existing = self.sessions_coll.get(ids=[session_id])
            if existing and existing.get("ids"):
                meta = existing["metadatas"][0]
                return {
                    "id": session_id,
                    "title": meta.get("title", "Consultation"),
                    "created_at": meta.get("created_at", now_iso),
                    "updated_at": meta.get("updated_at", now_iso),
                    "message_count": meta.get("message_count", 0),
                }

            # Create new
            initial_title = format_chat_title(title or "Nouvelle consultation")
            self.sessions_coll.add(
                ids=[session_id],
                documents=[initial_title],
                metadatas=[{
                    "title": initial_title,
                    "created_at": now_iso,
                    "updated_at": now_iso,
                    "message_count": 0,
                    **(context or {})
                }]
            )
            return {
                "id": session_id,
                "title": initial_title,
                "created_at": now_iso,
                "updated_at": now_iso,
                "message_count": 0
            }
        except Exception as e:
            logger.error(f"Error creating ChromaDB session {session_id}: {e}")
            return {"id": session_id, "title": title or "Consultation", "created_at": now_iso, "updated_at": now_iso}

    def save_message(self, session_id: str, role: str, content: str, sources: Optional[List[Dict[str, Any]]] = None) -> bool:
        """Saves a message turn and updates session metadata."""
        now_iso = datetime.now().isoformat()
        turn_id = f"{session_id}_{uuid4().hex}"

        try:
            # History storage must have a parent session even for the first turn.
            self.get_or_create_session(session_id)
            # Add message to messages collection
            meta = {
                "session_id": session_id,
                "role": role,
                "timestamp": now_iso,
                "sources_json": json.dumps(sources or [])
            }
            self.messages_coll.add(
                ids=[turn_id],
                documents=[content],
                metadatas=[meta]
            )

            # Update session in sessions collection
            session_data = self.sessions_coll.get(ids=[session_id])
            if session_data and session_data.get("ids"):
                current_meta = session_data["metadatas"][0]
                new_count = current_meta.get("message_count", 0) + 1
                
                # If title is generic and this is first user message, generate title from content
                current_title = current_meta.get("title", "")
                if (current_title in ("Nouvelle consultation", "Consultation", "") or not current_title) and role == "user":
                    new_title = format_chat_title(content[:35] + ("..." if len(content) > 35 else ""))
                else:
                    new_title = format_chat_title(current_title)

                self.sessions_coll.update(
                    ids=[session_id],
                    documents=[new_title],
                    metadatas=[{
                        **current_meta,
                        "title": new_title,
                        "updated_at": now_iso,
                        "message_count": new_count
                    }]
                )
            else:
                self.get_or_create_session(session_id, title=content[:35])
            return True

        except Exception as e:
            logger.error(f"Error saving message in ChromaDB for {session_id}: {e}")
            return False

    def get_session_history(self, session_id: str) -> List[Dict[str, Any]]:
        """Retrieves all messages for a given session sorted by timestamp."""
        try:
            results = self.messages_coll.get(
                where={"session_id": session_id}
            )
            messages = []
            if results and results.get("ids"):
                for idx, msg_id in enumerate(results["ids"]):
                    meta = results["metadatas"][idx]
                    sources_json = meta.get("sources_json", "[]")
                    try:
                        sources = json.loads(sources_json)
                    except Exception:
                        sources = []

                    messages.append({
                        "id": msg_id,
                        "role": meta.get("role", "assistant"),
                        "content": results["documents"][idx],
                        "timestamp": meta.get("timestamp", ""),
                        "sources": sources
                    })

            messages.sort(key=lambda m: m.get("timestamp", ""))
            return messages
        except Exception as e:
            logger.error(f"Error fetching session history from ChromaDB: {e}")
            return []

    def rename_session(self, session_id: str, new_title: str) -> bool:
        """Renames a session in ChromaDB with immediate metadata persistence."""
        now_iso = datetime.now().isoformat()
        try:
            session_data = self.sessions_coll.get(ids=[session_id])
            if session_data and session_data.get("ids"):
                meta = session_data["metadatas"][0]
                meta["title"] = format_chat_title(new_title)
                meta["updated_at"] = now_iso
                self.sessions_coll.update(
                    ids=[session_id],
                    documents=[meta["title"]],
                    metadatas=[meta]
                )
                logger.info(f"Renamed ChromaDB session {session_id} to '{meta['title']}'")
                return True
            return False
        except Exception as e:
            logger.error(f"Error renaming session {session_id}: {e}")
            return False

    def delete_session(self, session_id: str) -> bool:
        """Deletes session metadata and all associated messages from ChromaDB."""
        try:
            # Delete messages first
            self.messages_coll.delete(where={"session_id": session_id})
            # Delete session entry
            self.sessions_coll.delete(ids=[session_id])
            logger.info(f"Deleted ChromaDB session {session_id} and all its messages.")
            return True
        except Exception as e:
            logger.error(f"Error deleting session {session_id}: {e}")
            return False

    def search_past_context(self, query: str, top_k: int = 3) -> List[Dict[str, Any]]:
        """Vector semantic similarity search across past conversations."""
        try:
            results = self.messages_coll.query(
                query_texts=[query],
                n_results=top_k
            )
            hits = []
            if results and results.get("documents"):
                for idx, doc in enumerate(results["documents"][0]):
                    meta = results["metadatas"][0][idx]
                    hits.append({
                        "content": doc,
                        "role": meta.get("role"),
                        "session_id": meta.get("session_id"),
                        "timestamp": meta.get("timestamp")
                    })
            return hits
        except Exception as e:
            logger.warning(f"ChromaDB search_past_context warning: {e}")
            return []

