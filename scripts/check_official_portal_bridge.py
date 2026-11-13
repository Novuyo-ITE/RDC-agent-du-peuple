"""Real browser/form round-trip against a controlled test portal, never a citizen filing."""
import os
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'drc_gov_agent.settings')
import django
django.setup()
from apps.rag_engine.service_browser import OfficialPortalBrowser, PortalUnavailable

received = []
HTML = '''<html><head><title>Test application</title></head><body><form method="post" action="/submit">
<input type="hidden" name="csrf" value="official-csrf-token">
<label>Nom<input name="full_name" required></label><label>Courriel<input name="email" type="email" required></label>
<label>Mot de passe<input name="password" type="password"></label>
<label>Pièce jointe<input name="attachment" type="file"></label><button type="submit">Déposer la demande test</button>
</form></body></html>'''


class ContextProxy:
    def __init__(self, context):
        self.context = context
    def __getattr__(self, key):
        return getattr(self.context, key)
    def route(self, pattern, guard):
        def handle(route):
            if route.request.url == 'https://portal.example/form':
                route.fulfill(content_type='text/html', body=HTML)
            elif route.request.url == 'https://portal.example/submit':
                received.append(route.request.post_data)
                route.fulfill(content_type='text/html', body='<html><title>Official test response</title><body>Test receipt TEST-123</body></html>')
            else:
                route.abort()
        self.context.route(pattern, handle)


class BrowserProxy:
    def __init__(self, browser):
        self.browser = browser
    def __getattr__(self, key):
        return getattr(self.browser, key)
    def new_context(self, **kwargs):
        return ContextProxy(self.browser.new_context(**kwargs))


class TestBridge(OfficialPortalBrowser):
    def _launch(self):
        super()._launch()
        if not isinstance(self.browser, BrowserProxy):
            self.browser = BrowserProxy(self.browser)


bridge = TestBridge()
resources = [{'url': 'https://portal.example/form'}]
try:
    with patch('apps.rag_engine.service_browser.public_host', return_value=True):
        state = bridge.execute('citizen-a', 'service', 'start', {'url': resources[0]['url']}, resources)
        refs = {field['name']: field['ref'] for field in state['fields']}
        assert len(refs) == 4
        context = bridge.form_context('citizen-a', 'service')
        assert all(field['type'] not in ('password', 'file') for field in context['fields'])
        payload = {'action_id': 'unique-test-action-0001', 'button': state['buttons'][0]['ref'],
                   'values': {refs['full_name']: 'Test applicant', refs['email']: 'test@example.com', refs['password']: 'test-password'}}
        state = bridge.execute('citizen-a', 'service', 'button', payload, resources)
        assert state['title'] == 'Official test response'
        assert 'full_name=Test+applicant' in received[0]
        assert 'csrf=official-csrf-token' in received[0]
        bridge.execute('citizen-a', 'service', 'button', payload, resources)
        assert len(received) == 1, 'Repeated action must not submit again'
        assert bridge.form_context('citizen-b', 'service') is None
        bridge.execute('citizen-a', 'service', 'close', {}, resources)
        assert bridge.form_context('citizen-a', 'service') is None
        print('PASS: actual browser fills and submits test form, retains official CSRF, isolates sessions, and prevents duplicate actions')
finally:
    bridge.shutdown()
