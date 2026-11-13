"""Save public official source bodies through the configured Tavily account."""
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'drc_gov_agent.settings')
import django
django.setup()
from apps.rag_engine.web_search import TavilyDRCSearchTool

root = Path(__file__).resolve().parents[1]
sources = json.loads((root / 'apps/rag_engine/data/service_source_research.json').read_text(encoding='utf-8'))
urls = list(dict.fromkeys(url for group in sources.values() for url in group))
output = root / 'service_research'
output.mkdir(exist_ok=True)
tool = TavilyDRCSearchTool()
for index in range(0, len(urls), 20):
    result = tool.extract(urls[index:index + 20])
    (output / f'tavily-extract-{index}.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'retrieved': [item['url'] for item in result.get('results', [])],
                      'failed': [item['url'] for item in result.get('failed_results', [])]}), flush=True)
