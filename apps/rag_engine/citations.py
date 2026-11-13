"""Match explicit answer citations to retrieved pages, never just their domains."""
import re
from types import SimpleNamespace
from urllib.parse import urlsplit, urlunsplit


def cited_sources(answer, sources):
    def key(value):
        try:
            parts = urlsplit(value)
            if parts.scheme.lower() not in ('http', 'https') or not parts.hostname:
                return None
            return urlunsplit((parts.scheme.lower(), parts.netloc.lower(),
                              parts.path.rstrip('/'), parts.query, ''))
        except ValueError:
            return None
    urls = {key(url.rstrip('.,;:!?')) for url in re.findall(r'https?://[^\s<>"\)\]]+', answer)}
    urls.discard(None)
    result, seen = [], set()
    for source in sources:
        url = key(source.get('url', ''))
        if url and url in urls and url not in seen:
            result.append(source)
            seen.add(url)
    return result


def validate_citation_paragraphs(answer, sources):
    """Drop paragraphs containing invented URLs, rather than legitimising their claims."""
    paragraphs = re.split(r'(\n\s*\n)', answer)
    for index in range(0, len(paragraphs), 2):
        paragraph = paragraphs[index]
        urls = re.findall(r'https?://[^\s<>"\)\]]+', paragraph)
        for url in urls:
            if not cited_sources(url, sources):
                paragraphs[index] = ''
                break
    return ''.join(paragraphs)


def answer_references(answer, sources):
    """Keep retrieved articles visible without pretending the model cited them."""
    cited = cited_sources(answer, sources)
    cited_urls = {source.get('url') for source in cited}
    extra = []
    for source in sources:
        if source.get('url') in cited_urls or source.get('source_kind') == 'directory':
            continue
        if source.get('source_kind') == 'news' or source.get('image_url'):
            extra.append({**source, 'reference_only': True})
    # The UI shows up to three photographs while streaming. Keep those same
    # illustrated results in the saved answer even if text-only articles appear first.
    illustrated = [source for source in extra if source.get('image_url')][:3]
    text_only = [source for source in extra if not source.get('image_url')][:3]
    return cited + illustrated + text_only


def numbered_citation_chunks(chunks, sources):
    """Resolve numbered source labels to exact URLs while preserving streaming."""
    pending = ''

    def drain(final=False):
        nonlocal pending
        while pending:
            opening = re.search(r'[\[(]', pending)
            start = opening.start() if opening else -1
            if start < 0:
                yield SimpleNamespace(content=pending)
                pending = ''
                return
            if start:
                yield SimpleNamespace(content=pending[:start])
                pending = pending[start:]
            if pending.startswith('('):
                # Ordinary parenthesized prose must stream immediately. Only hold
                # text that could still become a numbered source reference.
                match = re.match(r'^\(\s*source\s*(\d+)\s*\)', pending, re.I)
                if match:
                    index = int(match.group(1)) - 1
                    url = sources[index].get('url', '') if 0 <= index < len(sources) else ''
                    label = f'[Source {index + 1}]({url})' if cited_sources(url, sources) else '[Source non disponible]'
                    yield SimpleNamespace(content=f'({label})')
                    pending = pending[match.end():]
                    continue
                possible = re.fullmatch(r'\(\s*(?:s(?:o(?:u(?:r(?:c(?:e\s*\d*\s*)?)?)?)?)?)?', pending, re.I)
                if possible and not final and len(pending) <= 96:
                    return
                yield SimpleNamespace(content=pending[:1])
                pending = pending[1:]
                continue
            end = pending.find(']')
            if end < 0:
                if not final and len(pending) <= 96 and '\n' not in pending:
                    return
                yield SimpleNamespace(content=pending[:1])
                pending = pending[1:]
                continue
            if end == len(pending) - 1 and not final:
                return  # A following '(' may make this an existing Markdown link.
            label, pending = pending[:end + 1], pending[end + 1:]
            match = re.fullmatch(r'\[\s*source\s*(\d+)\s*\]', label, re.I)
            if match and not pending.startswith('('):
                index = int(match.group(1)) - 1
                url = sources[index].get('url', '') if 0 <= index < len(sources) else ''
                label = f'[Source {index + 1}]({url})' if cited_sources(url, sources) else '[Source non disponible]'
            yield SimpleNamespace(content=label)

    try:
        for chunk in chunks:
            pending += chunk.content
            yield from drain()
        yield from drain(final=True)
    finally:
        close = getattr(chunks, 'close', None)
        if close:
            close()


def citation_chunks(chunks, sources):
    """Stream text immediately; buffer only URLs until they can be checked."""
    pending = ''

    def drain(final=False):
        nonlocal pending
        while pending:
            match = re.search(r'https?://', pending)
            if match:
                if match.start():
                    yield SimpleNamespace(content=pending[:match.start()])
                    pending = pending[match.start():]
                end = re.search(r'[\s<>"\)\]]', pending)
                if not end and not final:
                    return
                size = end.start() if end else len(pending)
                url, pending = pending[:size], pending[size:]
                # The shared Markdown sanitizer disables non-HTTP links.
                yield SimpleNamespace(content=url if cited_sources(url, sources) else 'about:invalid')
            else:
                keep = 0
                if not final:
                    for protocol in ('https://', 'http://'):
                        for length in range(1, len(protocol)):
                            if pending.endswith(protocol[:length]):
                                keep = max(keep, length)
                ready = pending[:-keep] if keep else pending
                pending = pending[-keep:] if keep else ''
                if ready:
                    yield SimpleNamespace(content=ready)
                return

    try:
        for chunk in chunks:
            pending += chunk.content
            yield from drain()
        yield from drain(final=True)
    finally:
        close = getattr(chunks, 'close', None)
        if close:
            close()
