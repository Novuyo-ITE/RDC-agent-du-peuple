"""Editorial discovery targets, not a verification badge or a ranking by followers.

Account identity references and review date are retained for future maintenance.
Only exact URL handles qualify; mentioning a name in a snippet does not qualify.
"""
REVIEWED_ON = '2026-11-06'
SOCIAL_ACCOUNTS = {
    'radiookapi': {'name': 'Radio Okapi', 'group': 'media', 'reference': 'https://x.com/radiookapi/with_replies'},
    'actualitecd': {'name': 'ACTUALITE.CD', 'group': 'media', 'reference': 'https://actualite.cd/'},
    'topcongo': {'name': 'TOP CONGO FM', 'group': 'media', 'reference': 'https://x.com/TopCongo/with_replies'},
    'stanysbujakera': {'name': 'Stanis Bujakera Tshiamala', 'group': 'voices', 'reference': 'https://x.com/StanysBujakera/status/951476281929097216'},
    'michombero': {'name': 'Daniel Michombero / Batubenga', 'group': 'voices', 'reference': 'https://x.com/michombero'},
    'denismukwege': {'name': 'Denis Mukwege', 'group': 'voices', 'reference': 'https://ishr.ch/defender-stories/defender-profile-dr-denis-mukwege-from-the-democratic-republic-of-the-congo/'},
    'lusengej': {'name': 'Julienne Lusenge', 'group': 'voices', 'reference': 'https://x.com/LusengeJ'},
    'martinfayulu': {'name': 'Martin Fayulu', 'group': 'public_figures', 'reference': 'https://x.com/MartinFayulu'},
    'moise_katumbi': {'name': 'Moïse Katumbi', 'group': 'public_figures', 'reference': 'https://x.com/moise_katumbi/status/645905853414014976'},
    'patrickmuyaya': {'name': 'Patrick Muyaya', 'group': 'public_figures', 'reference': 'https://x.com/PatrickMuyaya'},
    'presidence_rdc': {'name': 'Présidence RDC', 'group': 'institutions', 'reference': 'https://x.com/Presidence_RDC/with_replies'},
    'monusco': {'name': 'MONUSCO', 'group': 'institutions', 'reference': 'https://mobile.x.com/MONUSCO/with_replies'},
    'ambassaderdcfr': {'name': 'Ambassade RDC en France', 'group': 'embassies', 'reference': 'https://x.com/AmbassadeRDCFR'},
    'ambassaderdcbxl': {'name': 'Ambassade RDC à Bruxelles', 'group': 'embassies', 'reference': 'https://x.com/AmbassaderdcBxl/status/1785402502822662302'},
    'ambardcongousa': {'name': 'Ambassade RDC aux États-Unis', 'group': 'embassies', 'reference': 'https://x.com/AmbaRdcongoUsa'},
    'drcinuk': {'name': 'Ambassade RDC au Royaume-Uni', 'group': 'embassies', 'reference': 'https://x.com/DRCinUK'},
}
INSTAGRAM_ACCOUNTS = {
    'radiookapi': {'name': 'Radio Okapi', 'reference': 'https://www.instagram.com/radiookapi/'},
    'actualite.cd': {'name': 'ACTUALITE.CD', 'reference': 'https://www.instagram.com/actualite.cd/'},
}


def instagram_attribution(record):
    """Require publisher metadata, not a mention of the account in a caption."""
    import re
    from urllib.parse import urlsplit
    try:
        if (urlsplit(record.get('url', '')).hostname or '').removeprefix('www.') != 'instagram.com':
            return None
    except ValueError:
        return None
    snippet = record.get('snippet', '')
    if not isinstance(snippet, str):
        return None
    for handle, account in INSTAGRAM_ACCOUNTS.items():
        escaped = re.escape(handle)
        counts = rf'^\s*[\d.,KMk]+\s+likes?,\s*[\d.,KMk]+\s+comments?\s*[-–]\s*{escaped}\s+(?:on|op|le|am|em|en)\s+'
        byline = rf'^\s*(?:Photo|Video|Reel|Post) by (?:@?{escaped}|{re.escape(account["name"])})\s+on\s+'
        if re.search(counts, snippet, re.I) or re.search(byline, snippet, re.I):
            return handle
    return None


def account_from_url(url):
    from urllib.parse import urlsplit
    try:
        parsed = urlsplit(url)
        if (parsed.hostname or '').lower().removeprefix('www.').removeprefix('mobile.') not in ('x.com', 'twitter.com'):
            return None
        parts = parsed.path.strip('/').split('/')
        if len(parts) >= 3 and parts[1] == 'status':
            handle = parts[0].lower()
            if handle in SOCIAL_ACCOUNTS:
                return handle
    except (ValueError, TypeError):
        pass
    return None


def search_batches(offset=0):
    batches = []
    for group in ('media', 'voices', 'institutions', 'public_figures', 'embassies'):
        handles = [handle for handle, record in SOCIAL_ACCOUNTS.items() if record['group'] == group]
        handle = handles[offset % len(handles)]
        # Tavily performs better on a precise account name than a long Boolean
        # site: expression. Rotate one account per group on each refresh.
        name = SOCIAL_ACCOUNTS[handle]['name']
        batches.append({'domains': ['x.com', 'twitter.com'], 'query': f'{name} @{handle}', 'group': group})
    handle = list(INSTAGRAM_ACCOUNTS)[offset % len(INSTAGRAM_ACCOUNTS)]
    batches.append({'domains': ['instagram.com'], 'query': f'{INSTAGRAM_ACCOUNTS[handle]["name"]} @{handle} Instagram RDC'})
    return batches
