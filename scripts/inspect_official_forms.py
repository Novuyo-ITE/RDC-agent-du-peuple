"""Read public interactive portals without submitting or creating an account."""
import json
from pathlib import Path
import re
import sys
from playwright.sync_api import sync_playwright

sys.stdout.reconfigure(encoding='utf-8')
root = Path(__file__).resolve().parents[1] / 'service_research'
targets = {
    'evisa': 'https://evisa.gouv.cd/',
    'evisa-faq': 'https://evisa.gouv.cd/helps/faqs',
    'arsp': 'https://arsp.cd/enregistrement-et-demande-dagrement',
    'arsp-faq': 'https://arsp.cd/faq',
    'nif': 'https://e-nif.dgirdc.cd/',
}
with sync_playwright() as p:
    browser = p.chromium.launch(channel='msedge')
    context = browser.new_context(locale='fr-FR')
    for key, url in targets.items():
        page = context.new_page()
        try:
            page.goto(url, wait_until='domcontentloaded', timeout=45000)
            page.wait_for_timeout(2500)
            if key == 'arsp-faq':
                for button in page.locator('button').all():
                    if re.match(r'^\d+\s', button.inner_text().strip()):
                        try:
                            button.click(timeout=1000)
                        except Exception:
                            pass
            record = {'url': page.url, 'text': page.locator('body').inner_text(),
                      'links': page.locator('a[href]').evaluate_all('(els)=>els.map(e=>({label:e.textContent,url:e.href}))'),
                      'forms': page.locator('form').evaluate_all('(els)=>els.map(f=>({action:f.action,method:f.method,fields:[...f.elements].map(e=>({name:e.name,type:e.type,placeholder:e.placeholder,required:e.required}))}))')}
            (root / (key + '-rendered.json')).write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding='utf-8')
            (root / (key + '-rendered.html')).write_text(page.content(), encoding='utf-8')
            print(key, record['url'], record['text'][:700], 'FORMS', json.dumps(record['forms'], ensure_ascii=False)[:600], flush=True)
        except Exception as error:
            print(key, str(error)[:200], flush=True)
        page.close()
    browser.close()
