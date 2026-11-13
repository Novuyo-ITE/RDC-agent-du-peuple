"""Inspect public form entry points and expand official help text, without sending data."""
import json
from pathlib import Path
import sys
from playwright.sync_api import sync_playwright

sys.stdout.reconfigure(encoding='utf-8')
output = Path(__file__).resolve().parents[1] / 'service_research'
with sync_playwright() as p:
    browser = p.chromium.launch(channel='msedge')
    context = browser.new_context(locale='fr-FR')
    for name, url in [('evisa-register', 'https://evisa.gouv.cd/register'), ('arsp-application', 'https://arsp.cd/enregistrement-et-demande-dagrement'), ('arsp-answers', 'https://arsp.cd/faq')]:
        page = context.new_page()
        try:
            page.goto(url, wait_until='domcontentloaded', timeout=35000)
            page.wait_for_timeout(1800)
            collected = []
            if name == 'arsp-application':
                page.get_by_role('button', name='Démarrer mon enregistrement').first.click(force=True)
                page.wait_for_timeout(1000)
            elif name == 'arsp-answers':
                for pattern in ['Comment obtenir', 'Combien coûte', 'Combien dure', 'Comment recevoir', 'Comment savoir', 'Quels sont les documents']:
                    button = page.get_by_role('button').filter(has_text=pattern).first
                    if button.count():
                        button.click(force=True)
                        page.wait_for_timeout(200)
                        collected.append({'question': pattern, 'text': page.locator('body').inner_text()})
            record = {'url': page.url, 'text': page.locator('body').inner_text(), 'answers': collected,
                      'iframes': page.locator('iframe').evaluate_all('(els)=>els.map(e=>e.src)'),
                      'links': page.locator('a[href]').evaluate_all('(els)=>els.map(e=>({label:e.textContent,url:e.href}))'),
                      'controls': page.locator('input,select,textarea').evaluate_all('(els)=>els.map(e=>({name:e.name,id:e.id,type:e.type,placeholder:e.placeholder,required:e.required,label:e.labels?.[0]?.textContent,options:e.options?[...e.options].map(o=>({value:o.value,label:o.textContent})):undefined}))')}
            (output / (name + '.json')).write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding='utf-8')
            print(name, json.dumps({'url': record['url'], 'iframes': record['iframes'], 'controls': record['controls']}, ensure_ascii=False)[:2200], flush=True)
        except Exception as error:
            print(name, str(error)[:200], flush=True)
        page.close()
    browser.close()
