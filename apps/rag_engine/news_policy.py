"""Keep RFI coverage focused on the Democratic Republic of the Congo."""
import re
from urllib.parse import urlsplit
from django.db.models import Q

DRC_PATTERN = (r'(^|[^a-zA-Z0-9])(RDC|DRC|Kinshasa|Goma|Bukavu|Kivu|Ituri|Lubumbashi|Katanga|'
               r'Tshisekedi|FARDC|M23|Matadi|Bunia|Kisangani|Kananga|Mbuji[- ]Mayi)([^a-zA-Z0-9]|$)|'
               r'r[eé]publique\s+d[eé]mocratique\s+du\s+Congo|Democratic\s+Republic\s+of\s+(the\s+)?Congo|'
               r'Congo[- ]Kinshasa|(^|[^a-zA-Z])RD\s+Congo([^a-zA-Z]|$)')


def rfi_condition():
    return Q(source_name__istartswith='RFI') | Q(source_url__iregex=r'^https?://([^/]+\.)?rfi\.fr([/:?#]|$)')


def drc_condition():
    return Q(title__iregex=DRC_PATTERN) | Q(summary__iregex=DRC_PATTERN) | Q(full_content__iregex=DRC_PATTERN)


def news_allowed(source_name, source_url, title, summary='', content=''):
    try:
        host = (urlsplit(source_url).hostname or '').lower()
    except ValueError:
        host = ''
    rfi = source_name.upper().startswith('RFI') or host == 'rfi.fr' or host.endswith('.rfi.fr')
    return not rfi or bool(re.search(DRC_PATTERN, f'{title}\n{summary}\n{content}', re.I))
