"""Short, attributed source passages for chat source cards."""
import html
import re


def select_resource_sections(sections, query, limit=24000, max_sections=12):
    """Select bounded, relevant passages without losing their original page URLs."""
    stopwords = {'quel', 'quelle', 'quels', 'quelles', 'comment', 'pourquoi', 'source',
                 'article', 'document', 'explique', 'résume', 'resume', 'avec', 'dans', 'pour', 'cette'}
    terms = set(re.findall(r'\w{4,}', query.lower())) - stopwords
    scored = []
    for index, section in enumerate(sections):
        text = section.get('text', '')
        if not isinstance(text, str) or not text:
            continue
        title = str(section.get('title', '')).lower()
        lower = text.lower()
        score = sum(3 * (term in title) + (term in lower) for term in terms)
        scored.append((score, index, section))
    chosen = sorted(scored, key=lambda item: (-item[0], item[1]))[:max_sections]
    remaining = limit
    excerpts = []
    for _, index, section in chosen:
        if remaining <= 0:
            break
        text = section['text']
        budget = min(remaining, 6000 if len(chosen) > 1 else limit)
        position = min((text.lower().find(term) for term in terms if term in text.lower()), default=0)
        start = max(0, min(position - budget // 3, len(text) - budget)) if len(text) > budget else 0
        selected = text[start:start + budget]
        excerpts.append((index, {'title': section.get('title', ''), 'url': section.get('url', ''),
                                 'text': selected, 'partial': len(selected) < len(text)}))
        remaining -= len(selected)
    excerpts.sort(key=lambda item: item[0])
    return [item for _, item in excerpts]


def source_excerpt(text, limit=420):
    """Return a bounded passage, not an invented or model-generated summary."""
    if not isinstance(text, str):
        return ''
    text = html.unescape(re.sub(r'<[^>]+>', ' ', text))
    text = re.sub(r'!\[[^\]]*\]\([^)]*\)', ' ', text)
    text = re.sub(r'\[([^\]]+)\]\([^)]*\)', r'\1', text)
    text = re.sub(r'\s+', ' ', text).strip()
    if len(text) <= limit:
        return text
    shortened = text[:limit].rsplit(' ', 1)[0]
    return shortened.rstrip(' ,;:') + '…'


def snapshot_source_passages(snapshot, limit=420):
    """Collect material with its own page URL, including PDF section links."""
    if not snapshot.get('available'):
        return {}
    passages = {}

    def add(url, text):
        if isinstance(url, str) and url and isinstance(text, str) and text.strip():
            passages.setdefault(url, []).append(text.strip())

    for section in (snapshot.get('source_content') or {}).get('sections', []):
        if isinstance(section, dict):
            add(section.get('url'), section.get('text'))
    for value in snapshot.get('facts', {}).values():
        for fact in value if isinstance(value, list) else [value]:
            if isinstance(fact, dict):
                add(fact.get('url'), fact.get('text'))
    raw = snapshot.get('text') or ''
    if isinstance(raw, str):
        # Normal service snapshots concatenate fetched pages with explicit URL markers.
        parts = re.split(r'(?:^|\n\n)SOURCE: ([^\n]+)\n', raw)
        if len(parts) > 1:
            for index in range(1, len(parts) - 1, 2):
                add(parts[index].strip(), parts[index + 1])
        else:
            add(snapshot.get('source_url'), raw)
    return {url: source_excerpt(' '.join(items), limit=limit) for url, items in passages.items()}
