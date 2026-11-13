"""Browser regression checks with deterministic model/API replies, no user-data writes."""
import json
import os
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'drc_gov_agent.settings')
import django
django.setup()
from django.template.loader import render_to_string
from django.test import RequestFactory
from django.utils import timezone
from apps.rag_engine.models import OfficialNews
from playwright.sync_api import sync_playwright

article = OfficialNews(id=7, title='Memory test article', published_at=timezone.now(),
    summary='Test body', full_content='Test body', source_name='Official source', source_url='https://example.com/article')
news_html = render_to_string('news.html', {'news_list': [article], 'total_count': 1,
    'query': '', 'selected_category': 'all', 'current_period': 'all'}, request=RequestFactory().get('/news/'))
stored = {}
requests_seen = []

def stream(route):
    url = route.request.url
    if '/stream/' in url:
        query = parse_qs(urlsplit(url).query)
        sid = query['session_id'][0]
        stored.setdefault(sid, []).extend([{'role': 'user', 'content': query['query'][0]},
                                          {'role': 'assistant', 'content': 'Remembered reply'}])
        requests_seen.append({'session_id': sid})
    else:
        requests_seen.append(route.request.post_data_json)
    events = [{'type': 'token', 'token': 'Remembered reply'}, {'type': 'done', 'sources': []}]
    route.fulfill(content_type='text/event-stream', body=''.join('data: ' + json.dumps(e) + '\n\n' for e in events))

def api(route):
    url = route.request.url
    if '/stream/' in url or url.endswith('/guide/') or url.endswith('/chat/'):
        return stream(route)
    if url.endswith('/body/'):
        value = {'content': 'Test body', 'full_body_loaded': True}
    elif urlsplit(url).path == '/api/rag/sessions/':
        value = {'sessions': []}
    else:
        sid = urlsplit(url).path.strip('/').split('/')[-1]
        value = {'messages': stored.get(sid, [])}
    route.fulfill(content_type='application/json', body=json.dumps(value))

with sync_playwright() as p:
    browser = p.chromium.launch(channel='msedge')
    page = browser.new_page()
    errors = []
    page.on('pageerror', lambda error: errors.append(str(error)))
    page.route('**/api/rag/**', api)
    page.route('**/news/', lambda route: route.fulfill(content_type='text/html', body=news_html))
    page.goto('http://127.0.0.1:8001/chat/', wait_until='networkidle')
    page.locator('#query-input').fill('My name is Jean')
    page.evaluate('submitQuery()')
    page.wait_for_function('!chatBusy')
    first_session = requests_seen[-1]['session_id']
    page.reload(wait_until='networkidle')
    assert 'My name is Jean' in page.locator('#chat-messages').inner_text()
    assert 'Remembered reply' in page.locator('#chat-messages').inner_text()
    page.locator('#query-input').fill('What is my name?')
    page.evaluate('submitQuery()')
    page.wait_for_function('!chatBusy')
    assert requests_seen[-1]['session_id'] == first_session
    print('Main chat: same session and both roles restored after reload', flush=True)

    page.goto('http://127.0.0.1:8001/news/', wait_until='networkidle')
    page.evaluate('openNewsModal(7)')
    page.wait_for_function('!document.getElementById("article-chat-send").disabled')
    page.locator('#article-chat-input').fill('Please remember my question')
    page.evaluate('document.getElementById("article-chat-form").requestSubmit()')
    page.wait_for_function('!document.getElementById("article-chat-send").disabled')
    page.evaluate('closeNewsModal(); openNewsModal(7)')
    page.wait_for_function('!document.getElementById("article-chat-send").disabled')
    assert page.locator('#article-chat-messages > div').count() == 2
    page.reload(wait_until='networkidle')
    page.evaluate('openNewsModal(7)')
    page.wait_for_function('!document.getElementById("article-chat-send").disabled')
    assert page.locator('#article-chat-messages > div').count() == 2
    page.locator('#article-chat-input').fill('Continue')
    page.evaluate('document.getElementById("article-chat-form").requestSubmit()')
    page.wait_for_function('!document.getElementById("article-chat-send").disabled')
    assert [turn['role'] for turn in requests_seen[-1]['history']] == ['user', 'assistant']
    print('Article chat: both roles restored after reopening/reload and included in follow-up', flush=True)

    code = 'numero-identification-fiscale-dgi'
    old_history = [{'role': 'user' if i % 2 == 0 else 'assistant', 'content': f'Prior message {i}'} for i in range(14)]
    page.evaluate('([key,value])=>sessionStorage.setItem(key,JSON.stringify(value))', ['service-guide-history:' + code, old_history])
    page.goto('http://127.0.0.1:8001/demarches/' + code + '/', wait_until='networkidle')
    assert page.locator('#service-guide-messages .svc-message').count() == 14
    page.locator('#service-guide-query').fill('Continue the conversation')
    page.evaluate('document.getElementById("service-guide-form").requestSubmit()')
    page.wait_for_function('!document.getElementById("service-guide-send").disabled')
    assert requests_seen[-1]['history'] == old_history
    page.reload(wait_until='networkidle')
    assert page.locator('#service-guide-messages .svc-message').count() == 16
    print('Service guide: more than six exchanges retained and sent with follow-up', flush=True)
    assert not errors, errors
    browser.close()
