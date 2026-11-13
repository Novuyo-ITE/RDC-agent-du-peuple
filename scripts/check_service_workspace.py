"""Read-only browser verification of the persisted service dossiers."""
import json
from pathlib import Path
from playwright.sync_api import sync_playwright

root = Path(__file__).resolve().parents[1]
codes = json.loads((root / 'apps/rag_engine/data/service_dossiers.json').read_text(encoding='utf-8'))
with sync_playwright() as p:
    browser = p.chromium.launch(channel='msedge')
    page = browser.new_page(viewport={'width': 1440, 'height': 1000})
    errors = []
    page.on('pageerror', lambda error: errors.append(str(error)))
    for code in codes:
        page.goto('http://127.0.0.1:8001/demarches/' + code + '/', wait_until='networkidle')
        assert page.locator('#official-service-step-list li').count() >= 5, code
        assert page.locator('#live-service-documents li').count() >= 2, code
        page.locator('#tab-prepare').click()
        assert page.locator('#step-prepare [data-open-official-session]').count() >= 1, code
        page.locator('#tab-apply').click()
        assert page.locator('#step-apply [data-open-official-session]').count() >= 1, code
        print(json.dumps({'service': code, 'steps': page.locator('#official-service-step-list li').count(),
                          'draft_fields': page.locator('#official-form-draft input').count()}), flush=True)
    page.locator('#tab-understand').click()
    page.screenshot(path=str(root / 'services-dossier-preview.png'), full_page=True)
    page.set_viewport_size({'width': 390, 'height': 844})
    page.wait_for_function("document.getElementById('main-sidebar').getBoundingClientRect().right <= 1")
    page.screenshot(path=str(root / 'services-dossier-mobile-preview.png'), full_page=True)
    print(page.locator('.svc-shell,.svc-container,.svc-workspace,.svc-panel,.svc-workspace-head,main').evaluate_all(
        '(els)=>els.map(e=>({cls:e.className,w:e.clientWidth,scroll:e.scrollWidth,x:e.getBoundingClientRect().x}))'), flush=True)
    assert page.locator('.svc-shell').evaluate('(e)=>e.scrollWidth <= e.clientWidth'), 'Service content overflow'
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), 'Mobile overflow'
    assert not errors, errors
    browser.close()
