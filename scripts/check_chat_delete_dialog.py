"""Exercise the shared delete popup with isolated history fixtures (no real deletions)."""
import json
import os
import sys
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'drc_gov_agent.settings')
import django
django.setup()
from django.template.loader import render_to_string
from playwright.sync_api import sync_playwright, expect

html = render_to_string('base.html')
sessions = [{'id': 'demo_chat', 'title': 'Démarches pour un passeport', 'message_count': 4}]
deletions = []
fail_delete = True

def route_request(route):
    path = urlsplit(route.request.url).path
    if path.startswith('/static/'):
        asset = ROOT / path.lstrip('/')
        route.fulfill(path=str(asset)) if asset.is_file() else route.abort()
    elif path.endswith('/delete/'):
        deletions.append(path)
        if fail_delete:
            route.fulfill(status=500, content_type='application/json', body='{}')
        else:
            sessions.clear()
            route.fulfill(content_type='application/json', body='{"status":"success"}')
    elif path == '/api/rag/sessions/':
        route.fulfill(content_type='application/json', body=json.dumps({'sessions': sessions}))
    else:
        route.fulfill(content_type='text/html', body=html)

with sync_playwright() as p:
    browser = p.chromium.launch(channel='msedge')
    page = browser.new_page(viewport={'width': 1280, 'height': 800})
    errors = []
    page.on('pageerror', lambda error: errors.append(str(error)))
    page.route('**/*', route_request)
    page.route('https://**/*', lambda route: route.abort())
    page.goto('http://127.0.0.1:8001/chat/', wait_until='networkidle')
    trash = page.locator('#sess-item-demo_chat button[title="Supprimer"]')
    dialog = page.locator('#chat-delete-dialog')
    trash.click()
    expect(dialog).to_be_visible()
    expect(page.locator('#chat-delete-name')).to_have_text(sessions[0]['title'])
    expect(page.locator('#chat-delete-cancel')).to_be_focused()
    page.keyboard.press('Shift+Tab')
    expect(page.locator('#chat-delete-confirm')).to_be_focused()
    page.keyboard.press('Tab')
    expect(page.locator('#chat-delete-cancel')).to_be_focused()
    page.screenshot(path=str(ROOT / 'chat-delete-dialog-preview.png'))
    page.keyboard.press('Escape')
    expect(dialog).not_to_be_visible()
    expect(trash).to_be_focused()
    trash.click()
    page.locator('#chat-delete-cancel').click()
    expect(dialog).not_to_be_visible()
    trash.click()
    page.mouse.click(5, 5)
    expect(dialog).not_to_be_visible()
    assert not deletions
    trash.click()
    page.locator('#chat-delete-confirm').click()
    expect(page.locator('#chat-delete-error')).to_be_visible()
    expect(page.locator('#sess-item-demo_chat')).to_be_visible()
    expect(page.locator('#chat-delete-confirm')).to_be_enabled()
    # Check narrow screens and dark mode before retrying.
    page.set_viewport_size({'width': 390, 'height': 844})
    page.evaluate("document.documentElement.classList.add('dark')")
    box = dialog.bounding_box()
    assert box['x'] >= 0 and box['x'] + box['width'] <= 390
    page.screenshot(path=str(ROOT / 'chat-delete-dialog-mobile-preview.png'))
    page.evaluate("window.currentSessionId = 'demo_chat'; window.startNewChat = () => { window.didReset = true; }; window.addEventListener('chat-session-deleted', e => { window.deletedId = e.detail.id; });")
    fail_delete = False
    page.locator('#chat-delete-confirm').click()
    expect(dialog).not_to_be_visible()
    expect(page.locator('#sess-item-demo_chat')).to_have_count(0)
    expect(page.locator('#recent-consultations-list')).to_contain_text('Aucune consultation')
    assert page.evaluate('window.didReset && window.deletedId === "demo_chat"')
    assert len(deletions) == 2
    assert not errors, errors
    browser.close()
print('Delete popup: cancel, Escape, backdrop, focus, failure/retry, active chat, empty history and mobile checks passed.')
