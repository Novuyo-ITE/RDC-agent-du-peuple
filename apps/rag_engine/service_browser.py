"""Isolated, citizen-controlled official portal sessions, displayed inside Services.

No replayed HTTP forms: cookies, CSRF, validation and submission remain in the
real portal. All Playwright objects live on one worker thread. Nothing in this
module declares an application accepted; the portal's visible response is shown.
"""
import atexit
import base64
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
import ipaddress
import secrets
import socket
import time
from urllib.parse import urlsplit

from django.conf import settings
from django.http import JsonResponse
from django.views.decorators.http import require_POST


class PortalUnavailable(Exception):
    pass


def public_host(host):
    try:
        addresses = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
        return bool(addresses) and all(ipaddress.ip_address(item[4][0]).is_global for item in addresses)
    except (OSError, ValueError):
        return False


def portal_resources(service):
    snapshot = service.source_snapshot or {}
    resources = list(snapshot.get('form_resources', []))
    if service.official_portal_url and not any(r['url'] == service.official_portal_url for r in resources):
        resources.append({'url': service.official_portal_url, 'title': service.service_name})
    return resources


class OfficialPortalBrowser:
    idle_seconds = 20 * 60

    def __init__(self):
        self.worker = ThreadPoolExecutor(max_workers=1, thread_name_prefix='official-portal')
        self.sessions = {}
        self.playwright = self.browser = None

    def execute(self, owner, service_code, action, data, resources):
        try:
            return self.worker.submit(self._execute, owner, service_code, action, data, resources).result(timeout=40)
        except FutureTimeout:
            raise PortalUnavailable('Le portail répond lentement. Actualisez la session pour vérifier son état avant de réessayer un envoi.') from None

    def _launch(self):
        if self.browser and self.browser.is_connected():
            return
        from playwright.sync_api import sync_playwright
        self.playwright = sync_playwright().start()
        channel = getattr(settings, 'SERVICE_BROWSER_CHANNEL', '')
        self.browser = self.playwright.chromium.launch(headless=True, **({'channel': channel} if channel else {}))

    def _close(self, key):
        entry = self.sessions.pop(key, None)
        if entry:
            entry['context'].close()

    def _execute(self, owner, service_code, action, data, resources):
        from playwright.sync_api import Error as BrowserError
        key = (owner, service_code)
        for expired, entry in list(self.sessions.items()):
            if time.monotonic() - entry['used'] > self.idle_seconds:
                self._close(expired)
        if action == 'close':
            self._close(key)
            return {'active': False}
        try:
            if action == 'start':
                url = data.get('url')
                if url not in [r['url'] for r in resources] or urlsplit(url).scheme != 'https':
                    raise PortalUnavailable('Choisissez un accès officiel de cette démarche.')
                host = urlsplit(url).hostname
                if not host or not public_host(host):
                    raise PortalUnavailable('Le portail officiel est actuellement inaccessible.')
                self._launch()
                if key not in self.sessions and len(self.sessions) >= 8:
                    raise PortalUnavailable('Toutes les sessions sont occupées. Réessayez dans quelques instants.')
                self._close(key)
                allowed = {urlsplit(r['url']).hostname for r in resources}
                context = self.browser.new_context(viewport={'width': 1000, 'height': 720}, locale='fr-FR',
                                                   accept_downloads=False, service_workers='block')
                entry = {'context': context, 'page': context.new_page(), 'used': time.monotonic(),
                         'fields': {}, 'buttons': {}, 'actions': {}, 'allowed': allowed,
                         'hosts': {}, 'notice': ''}
                self.sessions[key] = entry

                def guard(route):
                    target = urlsplit(route.request.url)
                    host = target.hostname or ''
                    safe = entry['hosts'].setdefault(host, public_host(host)) if host not in entry['hosts'] else entry['hosts'][host]
                    trusted_frame = host in allowed or host in {'www.google.com', 'www.recaptcha.net', 'challenges.cloudflare.com'}
                    if target.scheme not in ('https', 'http') or not safe or (route.request.is_navigation_request() and not trusted_frame):
                        entry['notice'] = 'Une destination externe n’est pas prise en charge dans cette session.'
                        route.abort()
                    else:
                        route.continue_()

                context.route('**/*', guard)
                context.on('page', lambda page: entry.update(page=page))
                entry['page'].goto(url, wait_until='domcontentloaded', timeout=20000)
            entry = self.sessions.get(key)
            if not entry:
                raise PortalUnavailable('La session a expiré. Ouvrez à nouveau la démarche pour vous reconnecter.')
            entry['used'] = time.monotonic()
            page = entry['page']
            if action not in ('start', 'snapshot'):
                action_id = data.get('action_id')
                if not isinstance(action_id, str) or not 16 <= len(action_id) <= 100:
                    raise PortalUnavailable('Action invalide. Actualisez la session.')
                if action_id in entry['actions']:
                    return self._snapshot(entry)
                # Record before executing: retries must not repeat a submission.
                entry['actions'][action_id] = True
                if len(entry['actions']) > 100:
                    entry['actions'].pop(next(iter(entry['actions'])))
                if action == 'fill' or (action in ('button', 'upload') and data.get('values')):
                    values = data.get('values', {})
                    if not isinstance(values, dict) or len(values) > 80:
                        raise PortalUnavailable('Champs invalides.')
                    for ref, value in values.items():
                        field = entry['fields'].get(ref)
                        if not field or not isinstance(value, str) or len(value) > 8000:
                            raise PortalUnavailable('Le formulaire a changé. Actualisez les champs.')
                        control, kind = field
                        if kind == 'select':
                            control.select_option(value, timeout=5000)
                        elif kind == 'checkbox':
                            control.set_checked(value == 'true', timeout=5000)
                        elif kind == 'radio':
                            if value == 'true':
                                control.check(timeout=5000)
                        elif kind != 'file':
                            control.fill(value, timeout=5000)
                if action == 'button':
                    button = entry['buttons'].get(data.get('button'))
                    if button is None:
                        raise PortalUnavailable('Le bouton a changé. Actualisez la page.')
                    button.click(timeout=10000)
                elif action == 'click':
                    x, y = data.get('x'), data.get('y')
                    if type(x) not in (int, float) or type(y) not in (int, float) or not 0 <= x < 1000 or not 0 <= y < 720:
                        raise PortalUnavailable('Position invalide.')
                    page.mouse.click(x, y)
                elif action == 'scroll':
                    page.mouse.move(500, 350)
                    page.mouse.wheel(0, 550 if data.get('direction') == 'down' else -550)
                elif action == 'type':
                    value = data.get('value')
                    if not isinstance(value, str) or len(value) > 8000:
                        raise PortalUnavailable('Texte invalide.')
                    page.keyboard.insert_text(value)
                elif action == 'upload':
                    field = entry['fields'].get(data.get('field'))
                    if not field or field[1] != 'file':
                        raise PortalUnavailable('Sélectionnez un champ de pièce jointe actuel.')
                    field[0].set_input_files(data['file'], timeout=10000)
                elif action == 'back':
                    page.go_back(wait_until='domcontentloaded', timeout=15000)
                elif action != 'fill':
                    raise PortalUnavailable('Action non prise en charge.')
            # Allow DOM updates after clicks without waiting for analytics/network idle.
            entry['page'].wait_for_timeout(650)
            return self._snapshot(entry)
        except BrowserError:
            if action == 'start':
                self._close(key)
            raise PortalUnavailable('Le portail officiel n’a pas terminé cette action. Actualisez pour consulter son état ; aucun dépôt n’est confirmé par notre plateforme.') from None

    def _snapshot(self, entry):
        page = entry['page']
        entry['fields'], entry['buttons'] = {}, {}
        fields, buttons = [], []
        for frame in page.frames:
            if urlsplit(frame.url).hostname not in entry['allowed']:
                continue
            controls = frame.locator('input:not([type=hidden]):not([type=submit]):not([type=button]), select, textarea')
            for index in range(min(controls.count(), 80)):
                control = controls.nth(index)
                if not control.is_visible() or not control.is_enabled():
                    continue
                details = control.evaluate('''e=>({name:e.name || e.id, type:e.tagName==='SELECT'?'select':e.tagName==='TEXTAREA'?'textarea':e.type,
                    label:[...(e.labels || [])].map(l=>l.textContent.trim()).join(' ') || e.getAttribute('aria-label') || e.placeholder || e.name || e.id,
                    required:e.required, readOnly:e.readOnly, options:e.tagName==='SELECT'?[...e.options].map(o=>({value:o.value,label:o.textContent})):[]})''')
                if details['type'] not in ('text', 'email', 'tel', 'number', 'date', 'password', 'textarea', 'select', 'checkbox', 'radio', 'file', 'url') or details.get('readOnly'):
                    continue
                ref = secrets.token_hex(12)
                entry['fields'][ref] = (control, details['type'])
                if details['type'] in ('checkbox', 'radio'):
                    details['checked'] = control.is_checked()
                elif details['type'] not in ('file', 'password'):
                    details['value'] = control.input_value()
                fields.append({**details, 'ref': ref})
            elements = frame.locator('button, input[type=submit], [role=button]')
            for index in range(min(elements.count(), 50)):
                button = elements.nth(index)
                if not button.is_visible() or not button.is_enabled():
                    continue
                label = button.inner_text() or button.get_attribute('value') or button.get_attribute('aria-label')
                if not label or not label.strip():
                    continue
                ref = secrets.token_hex(12)
                entry['buttons'][ref] = button
                buttons.append({'ref': ref, 'label': label.strip()[:180]})
        import re
        entry['public_fields'] = [{**field, 'name': field['ref'], 'source_name': field['name']}
            for field in fields if field['type'] not in ('password', 'file', 'checkbox', 'radio')
            and not re.search(r'password|passwd|csrf|token|captcha|\botp\b|\bpin\b|verification|vérification',
                              (field.get('name') or '') + ' ' + field['label'], re.I)]
        for field in entry['public_fields']:
            field.pop('value', None)
        entry['page_title'] = page.title()
        entry['page_url'] = urlsplit(page.url)._replace(query='', fragment='').geturl()
        return {'active': True, 'url': page.url, 'title': page.title(), 'width': 1000, 'height': 720,
                'image': 'data:image/png;base64,' + base64.b64encode(page.screenshot()).decode('ascii'),
                'fields': fields, 'buttons': buttons, 'notice': entry['notice']}

    def form_context(self, owner, code):
        def describe():
            entry = self.sessions.get((owner, code))
            if not entry or time.monotonic() - entry['used'] > self.idle_seconds:
                return None
            return {'source_url': entry.get('page_url'), 'title': entry.get('page_title'),
                    'fields': entry.get('public_fields', [])}
        try:
            return self.worker.submit(describe).result(timeout=3)
        except FutureTimeout:
            return None

    def shutdown(self):
        def close():
            for key in list(self.sessions):
                self._close(key)
            if self.browser:
                self.browser.close()
            if self.playwright:
                self.playwright.stop()
        try:
            self.worker.submit(close).result(timeout=5)
        except Exception:
            pass
        self.worker.shutdown(wait=False, cancel_futures=True)


_browser = OfficialPortalBrowser()
atexit.register(_browser.shutdown)


def current_form_context(request, service_code):
    owner = request.session.get('official_browser_owner') if hasattr(request, 'session') else None
    return _browser.form_context(owner, service_code) if owner else None


@require_POST
def official_browser_action(request, service_code):
    import json
    from .service_assistance import resolve_service
    service = resolve_service(service_code)
    try:
        if request.content_type == 'multipart/form-data':
            data = request.POST.dict()
            data['values'] = json.loads(data.get('values', '{}'))
            upload = request.FILES.get('file')
            if not upload or upload.size > 10 * 1024 * 1024:
                raise ValueError()
            data['file'] = {'name': upload.name, 'mimeType': upload.content_type or 'application/octet-stream', 'buffer': upload.read()}
        else:
            data = json.loads(request.body)
        if not isinstance(data, dict):
            raise ValueError()
        action = data.get('action')
        if action not in ('start', 'snapshot', 'close', 'fill', 'button', 'click', 'scroll', 'type', 'upload', 'back'):
            raise ValueError()
        owner = request.session.get('official_browser_owner')
        if not owner:
            owner = secrets.token_hex(32)
            request.session['official_browser_owner'] = owner
        result = _browser.execute(owner, service.service_code, action, data, portal_resources(service))
        response = JsonResponse(result)
    except (ValueError, TypeError, AttributeError):
        response = JsonResponse({'error': 'Action ou pièce jointe invalide (10 Mo maximum).'}, status=400)
    except PortalUnavailable as error:
        response = JsonResponse({'error': str(error)}, status=409)
    except Exception:
        response = JsonResponse({'error': 'La session du portail est indisponible. Réessayez dans quelques instants.'}, status=503)
    response['Cache-Control'] = 'no-store'
    return response
