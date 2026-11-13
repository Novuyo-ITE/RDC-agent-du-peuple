"""Keep conversation roles intact while bounding the local model's context."""

MAX_HISTORY_MESSAGES = 100
MODEL_HISTORY_CHARACTERS = 16000


def read_history(value):
    """Validate client history; callers return 400 for invalid roles or payloads."""
    if not isinstance(value, list) or len(value) > MAX_HISTORY_MESSAGES:
        raise ValueError('Invalid conversation history')
    for turn in value:
        if (not isinstance(turn, dict) or turn.get('role') not in ('user', 'assistant')
                or not isinstance(turn.get('content'), str) or len(turn['content']) > 8000):
            raise ValueError('Invalid conversation message')
    return [{'role': turn['role'], 'content': turn['content']} for turn in value]


def model_history(history):
    """Take recent messages in chronological order, without promoting them to instructions."""
    selected, remaining = [], MODEL_HISTORY_CHARACTERS
    for turn in reversed(history):
        if turn.get('role') not in ('user', 'assistant') or not isinstance(turn.get('content'), str):
            continue
        content = turn['content']
        if not content.strip():
            continue
        if len(content) > remaining:
            # An oversized assistant turn must not erase all conversational context.
            content = content[:min(6000, remaining)]
        selected.append({'role': turn['role'], 'content': content})
        remaining -= len(content)
        if remaining <= 0:
            break
    selected.reverse()
    return selected


def retrieval_question(query, history):
    """Retain the preceding subject when a short question refers back to it."""
    import re
    from .news_answers import news_question
    # A fresh news request changes the subject, even after a procedural discussion.
    # Explicit references ("sur ce dossier") still retain the preceding subject.
    if (news_question(query)
            and not re.search(r'\b(?:ce|cet|cette|ces|cela|ça|this|that|it|its)\b', query, re.I)):
        return query
    referring_pattern = re.compile(
        r"^(et\b|and\b|combien\b|comment\b|où\b|pourquoi\b|quels?\b|quelles?\b|"
        r"what\b|how\b|where\b|why\b|ça\b|cela\b|ce\b|cette\b|ces\b)", re.I)
    if referring_pattern.match(query.strip()) and len(query.split()) <= 20:
        questions = [turn['content'] for turn in history if turn.get('role') == 'user']
        previous = next((text for text in reversed(questions) if not referring_pattern.match(text.strip())),
                        questions[-1] if questions else '')
        if previous:
            return previous[:1000] + '\nQuestion de suivi : ' + query
    return query
