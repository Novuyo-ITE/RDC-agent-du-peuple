"""Download public procedure pages for an auditable service-by-service review."""
import concurrent.futures
import hashlib
import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'drc_gov_agent.settings')
import django
django.setup()
import requests
from apps.rag_engine.official_service_portal import parse_official_page

root = Path(__file__).resolve().parents[1]
manifest = json.loads((root / 'apps/rag_engine/data/service_source_research.json').read_text(encoding='utf-8'))
output = root / 'service_research'
output.mkdir(exist_ok=True)


def fetch(url):
    name = hashlib.sha256(url.encode()).hexdigest()[:16]
    try:
        response = requests.get(url, timeout=(6, 20), headers={'User-Agent': 'Mozilla/5.0', 'Accept-Language': 'fr-FR,fr;q=0.9'})
        response.raise_for_status()
        if response.encoding == 'ISO-8859-1':
            response.encoding = response.apparent_encoding
        (output / (name + '.html')).write_text(response.text, encoding='utf-8')
        page = parse_official_page(response.text, response.url)
        record = {'requested_url': url, 'url': response.url, 'html_file': name + '.html', **page}
        (output / (name + '.json')).write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding='utf-8')
        return url, {'file': name + '.json', 'url': response.url, 'characters': len(page['text']), 'forms': len(page['forms'])}
    except Exception as error:
        return url, {'error': str(error)}


urls = list(dict.fromkeys(url for sources in manifest.values() for url in sources))
with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
    records = dict(executor.map(fetch, urls))
(output / 'index.json').write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding='utf-8')
for code, sources in manifest.items():
    print(code, json.dumps({url: records[url] for url in sources}, ensure_ascii=True), flush=True)
