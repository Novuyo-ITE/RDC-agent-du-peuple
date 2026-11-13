"""Browser UI regression with a deterministic official-session response."""
import json
from pathlib import Path
from playwright.sync_api import sync_playwright

root = Path(__file__).resolve().parents[1]
actions = []
state = {'active': True, 'url': 'https://evisa.gouv.cd/register', 'title': 'Créer un compte',
         'fields': [{'ref': 'name-ref', 'name': 'name', 'label': 'Nom', 'type': 'text', 'required': True},
                    {'ref': 'secret-ref', 'name': 'password', 'label': 'Mot de passe', 'type': 'password'}],
         'buttons': [{'ref': 'submit-ref', 'label': 'Créer mon compte'}],
         'image': 'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII='}

def respond(route):
    data = route.request.post_data_json
    actions.append(data)
    result = dict(state)
    if data['action'] == 'close':
        result = {'active': False}
    elif data['action'] == 'button':
        result.update(title='Réponse du portail test', fields=[], buttons=[])
    route.fulfill(content_type='application/json', body=json.dumps(result))

with sync_playwright() as p:
    browser = p.chromium.launch(channel='msedge')
    page = browser.new_page(viewport={'width': 1440, 'height': 1000})
    errors = []
    page.on('pageerror', lambda error: errors.append(str(error)))
    page.route('**/api/rag/services/*/browser/', respond)
    page.goto('http://127.0.0.1:8001/demarches/visa-electronique-rdc-evisa/', wait_until='networkidle')
    page.locator('#tab-prepare').click()
    page.locator('[data-open-official-session="https://evisa.gouv.cd/register"]').first.click()
    page.locator('#portal-field-name-ref').fill('Test applicant')
    page.locator('#portal-field-secret-ref').fill('test-password')
    page.locator('#official-browser-buttons button').first.click()
    page.wait_for_function("document.getElementById('official-browser-url').textContent.includes('Réponse du portail test')")
    assert actions[-1]['values'] == {'name-ref': 'Test applicant', 'secret-ref': 'test-password'}
    assert actions[-1]['button'] == 'submit-ref'
    page.locator('#official-browser-close').click()
    page.wait_for_function("document.getElementById('official-browser').hidden")
    assert not page.locator('#official-browser-fields input').count()
    assert not errors, errors
    page.set_viewport_size({'width': 390, 'height': 844})
    page.wait_for_function("document.getElementById('main-sidebar').getBoundingClientRect().right <= 1")
    assert page.locator('.svc-shell').evaluate('(e)=>e.scrollWidth <= e.clientWidth')
    print('PASS: in-page form values sent with actual button action, credentials cleared on close, mobile layout fits')
    browser.close()
