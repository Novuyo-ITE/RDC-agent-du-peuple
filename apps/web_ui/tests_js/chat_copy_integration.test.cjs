const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

function node() {
  return {children: [], textContent: '', append(child) { this.children.push(child); },
    appendChild(child) { this.children.push(child); }};
}

test('service messages keep the copy control outside the streamed Markdown', () => {
  const script = fs.readFileSync(path.join(__dirname, '../../../static/js/services.js'), 'utf8');
  const start = script.indexOf('    function appendMessage(role, text, sources = [])');
  const end = script.indexOf('    try {', start);
  const calls = [], log = node();
  const copy = {attach(message, text, role) { calls.push({message, text, role}); }};
  const context = {element(tag, className, text) { const item = node(); item.className = className; item.textContent = text || ''; return item; },
    window: {ChatCopy: copy}, ChatCopy: copy,
    ChatMarkdown: {render(content, text) { content.rendered = text; }}, log};
  vm.runInNewContext(script.slice(start, end), context);
  const answer = context.appendMessage('assistant', '**Réponse**');
  assert.equal(answer._chatCopyContent.rendered, '**Réponse**');
  assert.equal(calls[0].message, answer);
  assert.equal(calls[0].text, '**Réponse**');
  assert.equal(calls[0].role, 'assistant');
  const question = context.appendMessage('user', 'Ma question');
  assert.equal(question._chatCopyContent.textContent, 'Ma question');
  assert.equal(calls[1].role, 'user');
});

test('news chat attaches copy to each message while keeping a separate Markdown target', () => {
  const template = fs.readFileSync(path.join(__dirname, '../templates/news.html'), 'utf8');
  const start = template.indexOf('function appendArticleMessage(role,text,sources=[])');
  const end = template.indexOf("document.getElementById('article-chat-form').addEventListener", start);
  const calls = [], log = node();
  const copy = {attach(message, text, role) { calls.push({message, text, role}); }};
  const context = {document: {querySelector() { return null; }, createElement: node, getElementById() { return log; }},
    window: {ChatCopy: copy}, ChatCopy: copy, articleSuggestionsRequest: null,
    ChatMarkdown: {render(content, text) { content.rendered = text; }}};
  vm.runInNewContext(template.slice(start, end), context);
  const answer = context.appendArticleMessage('assistant', 'Réponse en **gras**');
  assert.equal(answer._chatCopyContent.rendered, 'Réponse en **gras**');
  assert.equal(calls[0].message, answer);
  assert.equal(calls[0].text, 'Réponse en **gras**');
  const question = context.appendArticleMessage('user', 'Pourquoi ?');
  assert.equal(question._chatCopyContent.textContent, 'Pourquoi ?');
  assert.equal(calls[1].role, 'user');
});
