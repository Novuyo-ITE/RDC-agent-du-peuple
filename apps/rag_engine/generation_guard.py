"""Bound streamed output and close the upstream request on repetition."""
import logging
import re
import time

logger = logging.getLogger(__name__)


def bounded_chunks(chunks, max_chars=14000, max_seconds=120):
    started = time.monotonic()
    output = ''
    try:
        for chunk in chunks:
            text = chunk.content
            if not isinstance(text, str):
                continue
            candidate = output + text
            tail = re.sub(r'\s+', ' ', candidate[-4000:]).strip().casefold()
            repeated = re.search(r'(.{30,800}?)\s*\1\s*\1', tail)
            if len(candidate) > max_chars or time.monotonic() - started > max_seconds or repeated:
                logger.warning('Stopped AI stream: %s', 'repetition' if repeated else 'output/time limit')
                break
            output = candidate
            yield chunk
    finally:
        close = getattr(chunks, 'close', None)
        if close:
            close()
