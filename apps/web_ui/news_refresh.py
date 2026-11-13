"""Refresh RSS articles without holding up page requests."""

import logging
import threading
import time

from django.db import close_old_connections

logger = logging.getLogger(__name__)
_lock = threading.Lock()
_last_started = None
_running = False


def refresh_news_if_due():
    """Start at most one refresh per minute in this web process."""
    global _last_started, _running
    with _lock:
        now = time.monotonic()
        if _running or (_last_started is not None and now - _last_started < 60):
            return
        _last_started = now
        _running = True
    threading.Thread(target=_refresh, name="news-refresh", daemon=True).start()


def _refresh():
    global _running
    close_old_connections()
    try:
        from apps.rag_engine.management.commands.fetch_drc_news import DRC_RSS_SOURCES, fetch_feed

        for source in DRC_RSS_SOURCES:
            try:
                fetch_feed(source, max_items=50)
            except Exception:
                logger.exception("News refresh failed for %s", source["name"])
    except Exception:
        logger.exception("Could not refresh news")
    finally:
        close_old_connections()
        with _lock:
            _running = False
