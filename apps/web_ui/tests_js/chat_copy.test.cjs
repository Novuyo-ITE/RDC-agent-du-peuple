const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const source = fs.readFileSync(path.join(__dirname, '../../../static/js/chat-copy.js'), 'utf8');

function fixture(clipboard, fallbackResult = true) {
  let selected = null, copied = null, focused = false, pointerdown;
  function element(tag) {
    return {tag, children: [], style: {}, attributes: {}, isConnected: true,
      classList: {add(name) { this[name] = true; }, remove(name) { delete this[name]; }},
      setAttribute(name, value) { this.attributes[name] = value; },
      append(child) { this.children.push(child); },
      addEventListener(type, fn) { this[type] = fn; },
      select() { selected = this; }, remove() { this.removed = true; },
      focus() { focused = true; }};
  }
  const previous = element('button');
  const document = {activeElement: previous, createElement: element,
    body: element('body'), addEventListener(type, fn) { if (type === 'pointerdown') pointerdown = fn; },
    execCommand() { copied = selected.value; return fallbackResult; }};
  const window = {setTimeout() { return 1; }, clearTimeout() {}};
  const navigator = {clipboard};
  vm.runInNewContext(source, {window, document, navigator});
  return {api: window.ChatCopy, element, pointerdown: event => pointerdown(event), get copied() { return copied; }, get focused() { return focused; }};
}

test('copies the current message text and reveals the button when streaming begins', async () => {
  const writes = [];
  const item = fixture({writeText: async value => writes.push(value)});
  const message = item.element('div');
  item.api.attach(message, '', 'assistant');
  assert.equal(message.classList['chat-copy-container'], true);
  const button = message.children[0];
  assert.equal(button.hidden, true);
  item.api.setText(message, '## Réponse\n\n- Premier point\n- Deuxième point');
  assert.equal(button.hidden, false);
  await button.click();
  assert.equal(writes[0], '## Réponse\n\n- Premier point\n- Deuxième point');
  assert.equal(button.children[0].textContent, 'Copié !');
  assert.equal(button.attributes['aria-label'], 'Copier la réponse');
});

test('touch reveals copy for the selected message and hides it on tapping elsewhere', () => {
  const item = fixture(null), first = item.element('div'), second = item.element('div');
  item.api.attach(first, 'Question', 'user');
  item.api.attach(second, 'Réponse', 'assistant');
  item.pointerdown({pointerType: 'touch', target: {closest: () => first}});
  assert.equal(first.classList['is-copy-active'], true);
  item.pointerdown({pointerType: 'touch', target: {closest: () => second}});
  assert.equal(first.classList['is-copy-active'], undefined);
  assert.equal(second.classList['is-copy-active'], true);
  item.pointerdown({pointerType: 'touch', target: {closest: () => null}});
  assert.equal(second.classList['is-copy-active'], undefined);
});

test('uses a local browser fallback and reports an unsuccessful copy', async () => {
  const rejected = {writeText: async () => { throw Error('denied'); }};
  const item = fixture(rejected);
  const message = item.element('div');
  item.api.attach(message, 'Ma question', 'user');
  await message.children[0].click();
  assert.equal(item.copied, 'Ma question');
  assert.equal(item.focused, true);
  const failure = fixture(rejected, false);
  const other = failure.element('div');
  failure.api.attach(other, 'Texte', 'user');
  await other.children[0].click();
  assert.equal(other.children[0].children[0].textContent, 'Copie impossible');
});
