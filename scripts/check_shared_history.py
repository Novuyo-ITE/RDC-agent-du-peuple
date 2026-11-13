"""Verify article/service conversations appear in and resume from common history.

API fixtures avoid writing test conversations to the user's persistent store.
"""
import json
import os
import sys
from pathlib import Path
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'drc_gov_agent.settings')
import django
django.setup()
from django.template.loader import render_to_string
from django.test import RequestFactory
from apps.rag_engine.chroma_session_manager import session_destination
from playwright.sync_api import sync_playwright

article = {'id': '7', 'title': 'Test actualité', 'category': 'Société', 'region': 'National',
           'date': '03/11/2026', 'source': 'Source', 'url': 'https://example.com/article',
           'image': '', 'full': 'Texte de test', 'summary': 'Résumé de test'}
news = render_to_string('news.html', {'news_list': [], 'deep_link_article': article,
    'selected_category': 'all', 'query': '', 'current_period': 'all'}, request=RequestFactory().get('/actualites/'))
sessions, messages, sent = {}, {}, []

def api(route):
    path = urlsplit(route.request.url).path
    if path == '/api/rag/sessions/import/':
        data = route.request.post_data_json
        sid = data['session_id']
        assert route.request.headers.get('x-csrftoken')
        meta = {'kind': data['kind'], 'article_id': int(data['context_id'])} if data['kind'] == 'article' else {'kind': 'service', 'service_code': data['context_id']}
        sessions[sid] = {**meta, 'id': sid, 'title': 'Imported ' + data['kind'], 'url': session_destination(sid, meta), 'message_count': len(data['messages'])}
        messages[sid] = data['messages']
        value = {'history_saved': True, 'session_id': sid}
    elif path.endswith('/body/'):
        value = {'content': article['full'], 'full_body_loaded': True}
    elif path.endswith('/chat/') or path.endswith('/guide/'):
        data = route.request.post_data_json
        sent.append(data)
        sid = data['session_id']
        meta = {'kind': 'article', 'article_id': 7} if path.endswith('/chat/') else {
            'kind': 'service', 'service_code': 'numero-identification-fiscale-dgi'}
        sessions[sid] = {**meta, 'id': sid, 'title': 'Actualité · Test' if meta['kind'] == 'article' else 'Service · NIF',
                         'url': session_destination(sid, meta), 'message_count': 2}
        messages.setdefault(sid, []).extend([{'role': 'user', 'content': data['query']}, {'role': 'assistant', 'content': 'Réponse sauvegardée'}])
        events = [{'type': 'token', 'token': 'Réponse sauvegardée'},
                  {'type': 'done', 'session_id': sid, 'history_saved': True, 'sources': []}]
        route.fulfill(content_type='text/event-stream', body=''.join('data: ' + json.dumps(e) + '\n\n' for e in events))
        return
    elif path == '/api/rag/sessions/':
        value = {'sessions': list(sessions.values())}
    else:
        sid = path.strip('/').split('/')[-1]
        value = {'session_id': sid, 'session': sessions.get(sid), 'messages': messages.get(sid, [])}
    route.fulfill(content_type='application/json', body=json.dumps(value))

with sync_playwright() as p:
    browser = p.chromium.launch(channel='msedge')
    page = browser.new_page()
    errors = []
    page.on('pageerror', lambda error: errors.append(str(error)))
    page.route('https://**/*', lambda route: route.abort())
    page.route('**/api/rag/**', api)
    page.route('**/actualites/**', lambda route: route.fulfill(content_type='text/html', body=news))
    page.goto('http://127.0.0.1:8001/actualites/?article=7', wait_until='networkidle')
    page.wait_for_function('!document.getElementById("article-chat-send").disabled')
    page.locator('#article-chat-input').fill('Ma question sur cette actualité')
    page.evaluate('document.getElementById("article-chat-form").requestSubmit()')
    page.wait_for_function('!document.getElementById("article-chat-send").disabled')
    article_session = sent[-1]['session_id']
    page.locator('[data-session-open]').filter(has_text='Actualité').wait_for()

    page.goto('http://127.0.0.1:8001/demarches/numero-identification-fiscale-dgi/', wait_until='networkidle')
    page.locator('#service-guide-query').fill('Ma question sur le NIF')
    page.evaluate('document.getElementById("service-guide-form").requestSubmit()')
    page.wait_for_function('!document.getElementById("service-guide-send").disabled')
    service_session = sent[-1]['session_id']
    page.locator('[data-session-open]').filter(has_text='Service').wait_for()
    page.locator('[data-session-open]').filter(has_text='Actualité').click()
    page.wait_for_url('**/actualites/?article=7&session=*')
    page.wait_for_function('!document.getElementById("article-chat-send").disabled')
    assert 'Ma question sur cette actualité' in page.locator('#article-chat-messages').inner_text()
    assert 'Réponse sauvegardée' in page.locator('#article-chat-messages').inner_text()
    page.locator('[data-session-open]').filter(has_text='Service').click()
    page.wait_for_url('**/demarches/numero-identification-fiscale-dgi/?session=*')
    page.wait_for_function('!document.getElementById("service-guide-send").disabled')
    assert 'Ma question sur le NIF' in page.locator('#service-guide-messages').inner_text()
    assert 'Réponse sauvegardée' in page.locator('#service-guide-messages').inner_text()
    page.locator('#service-guide-query').fill('Et ensuite ?')
    page.evaluate('document.getElementById("service-guide-form").requestSubmit()')
    page.wait_for_function('!document.getElementById("service-guide-send").disabled')
    assert sent[-1]['session_id'] == service_session
    assert [turn['role'] for turn in sent[-1]['history']] == ['user', 'assistant']
    page.evaluate("renderSessionItem({id:'capitalization_check',title:'échange sur les services',kind:'chat'})")
    assert page.locator('#title-capitalization_check').inner_text() == 'Échange sur les services'
    assert page.locator('#sess-item-capitalization_check [data-session-open] svg, #sess-item-capitalization_check [data-session-open] i').count() == 0
    legacy = browser.new_page()
    legacy.route('https://**/*', lambda route: route.abort())
    legacy.route('**/api/rag/**', api)
    legacy.add_init_script('''sessionStorage.setItem('article-chat-history:7',JSON.stringify([{role:'user',content:'Old article question'},{role:'assistant',content:'Old article answer'}]));
        sessionStorage.setItem('service-guide-history:numero-identification-fiscale-dgi',JSON.stringify([{role:'user',content:'Old service question'},{role:'assistant',content:'Old service answer'}]));''')
    legacy.goto('http://127.0.0.1:8001/chat/', wait_until='networkidle')
    legacy.locator('[data-session-open]').filter(has_text='Imported article').wait_for()
    legacy.locator('[data-session-open]').filter(has_text='Imported service').wait_for()
    assert any(turns[0]['content'] == 'Old article question' for turns in messages.values())
    assert any(turns[0]['content'] == 'Old service question' for turns in messages.values())
    legacy.close()
    assert not errors, errors
    browser.close()
    print('PASS: article/service chats join common history, resume with both roles, and import older tab-only conversations')
