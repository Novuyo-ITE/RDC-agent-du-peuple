"""Conservative extraction of a social post, without rewriting or adding facts."""
import html
import re

NORMALIZATION_VERSION = 2


def plain(value):
    value = html.unescape(value or '')
    value = re.sub(r'\\([_#*\[\]()!>])', r'\1', value)
    value = re.sub(r'\[([^\]]+)\]\(https?://[^)]+\)', r'\1', value)
    value = re.sub(r'<[^>]+>', '', value)
    return value.replace('\r\n', '\n').strip()


def extract_post(title, snippet):
    """Prefer the explicitly quoted main post over surrounding scraped discussion."""
    title, snippet = plain(title), plain(snippet)
    # The search snippet may start with a shortened page title. The Post section
    # contains the longer original quotation; never prefer the shortened title.
    section = re.split(r'(?im)^\s*##\s*Post\b[.\s]*', snippet, maxsplit=1)
    candidate = section[-1] if len(section) > 1 else snippet
    quoted = re.search(r'(?:on X|sur X|on Twitter)\s*:\s*["“](.*?)["”](?=\s*(?:/\s*(?:X|Twitter)\b|\.|$))', candidate, re.DOTALL)
    method = 'quoted_post' if quoted else 'clean_excerpt'
    if quoted:
        body = quoted.group(1)
    else:
        # Without a safely closed quote, retain only text preceding the original
        # timestamp. Everything after it can belong to other accounts' replies.
        body = re.split(r'\b\d{1,2}:\d{2}(?::\d{2})?\s*(?:AM|PM)?\s*[·•]', candidate, maxsplit=1, flags=re.I)[0]
        body = re.sub(r'(?im)^\s*Title\s*:[^\n]*(?:\n|$)', '', body)
        body = re.sub(r'(?im)^\s*#{1,6}\s+(?:Post\.?|Conversation|Conversa|Thread)\s*$', '', body)
        # A partially captured quoted post cannot safely be separated from replies.
        if re.search(r'(?:on X|sur X|on Twitter)\s*:', body):
            return None
        body = re.sub(r'^\s*(?:Conversation|Post)\s*[·.]\s*@[\w_]+\s*[·.]\s*[^·\n]{1,120}\s*[·.]\s*@[\w_]+[.·\s]*', '', body, flags=re.I)
        body = re.sub(r'\b(?:Show translation|Translate post)\.?\s*', '', body, flags=re.I)
        body = re.split(r'(?:\n|[·])\s*(?:Replying to|Replies)\b', body, maxsplit=1, flags=re.I)[0]
    body = re.split(r'(?im)(?:\bSee more posts\b|\bShow more replies\b|\bDiscover more\b|\bLog inSign up\b)', body)[0]
    body = re.sub(r'(?im)^\s*(?:Photo|Video) by .*(?:\n|$)', '', body)
    body = re.sub(r'(?im)^\s*#{1,6}\s+', '', body)
    body = re.sub(r'(?i)(?:\.\.\.|…)\s*Read more\s*$', '…', body)
    body = re.sub(r'(?i)\s*Read more\s*$', '', body)
    body = re.sub(r'\*{1,2}|`', '', body)
    body = re.sub(r'#([\w]+)', lambda match: match.group(1).replace('_', ' '), body)
    body = re.sub(r'[ \t\u00a0]+', ' ', body)
    body = re.sub(r'\n{3,}', '\n\n', body).strip(' \n#')
    if len(body) < 30 or not re.search(r'[A-Za-zÀ-ÿ]{3}', body):
        return None
    # Deduplicate exact paragraphs and add paragraph breaks at sentence boundaries.
    paragraphs = list(dict.fromkeys(part.strip() for part in body.split('\n\n') if part.strip()))
    readable = []
    for paragraph in paragraphs:
        chunk = ''
        for sentence in re.split(r'(?<=[.!?])\s+(?=[A-ZÀ-Ÿ«])', paragraph):
            if chunk and len(chunk) + len(sentence) > 420:
                readable.append(chunk); chunk = ''
            chunk = (chunk + ' ' + sentence).strip()
        if chunk:
            readable.append(chunk)
    body = '\n\n'.join(readable)
    first = re.split(r'(?<=[.!?])\s+', body)[0].replace('\n', ' ')
    headline = first if len(first) <= 160 else first[:157].rsplit(' ', 1)[0] + '…'
    return {'title': headline, 'body': body, 'method': method, 'version': NORMALIZATION_VERSION}
