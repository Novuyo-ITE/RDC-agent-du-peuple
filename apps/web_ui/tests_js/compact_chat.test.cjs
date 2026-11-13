const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const source = fs.readFileSync(path.join(__dirname, '../../../static/js/compact-chat.js'), 'utf8');

test('contextual chat microphone transcribes audio and reports server errors', async () => {
  const classes = new Set(), attrs = {}, track = {stopped: false, stop() { this.stopped = true; }};
  const input = {value: '', focus() {}, dispatchEvent() {}}, status = {textContent: ''};
  let listener, ready, recorder, result = {status: 'success', text: 'Bonjour'};
  const mic = {dataset: {target: 'input', status: 'status'}, disabled: false,
    classList: {add(name) { classes.add(name); }, remove(name) { classes.delete(name); }},
    addEventListener(type, callback) { listener = callback; }, setAttribute(name, value) { attrs[name] = value; }};
  class MediaRecorder {
    constructor(stream) { this.stream = stream; this.state = 'inactive'; recorder = this; }
    start() { this.state = 'recording'; }
    stop() { this.state = 'inactive'; }
  }
  const context = {window: {}, document: {addEventListener(type, callback) { ready = callback; },
    querySelectorAll() { return [mic]; }, getElementById(id) { return id === 'input' ? input : status; }},
    navigator: {mediaDevices: {getUserMedia: async () => ({getTracks: () => [track]})}},
    localStorage: {getItem() { return 'fr'; }}, MediaRecorder, Blob, FormData, Event,
    fetch: async () => ({ok: true, json: async () => result}), console};
  vm.runInNewContext(source, context); ready();
  await listener();
  assert.equal(classes.has('is-recording'), true);
  recorder.ondataavailable({data: new Blob(['audio'])});
  await listener();
  assert.equal(track.stopped, true);
  await recorder.onstop();
  assert.equal(input.value, 'Bonjour');
  assert.equal(status.textContent, '');
  assert.equal(attrs['aria-busy'], 'false');
  result = {status: 'error', error: 'Moteur indisponible'};
  await listener();
  recorder.ondataavailable({data: new Blob(['audio'])});
  await listener();
  await recorder.onstop();
  assert.equal(input.value, 'Bonjour');
  assert.equal(status.textContent, 'Moteur indisponible');
  assert.equal(mic.disabled, false);
});

test('send control exposes an actionable stop state and returns to send', () => {
  let ready;
  const context = {window: {}, document: {addEventListener(type, callback) { ready = callback; }}};
  vm.runInNewContext(source, context);
  const names = new Set(), sendIcon = {}, stopIcon = {};
  const button = {dataset: {}, classList: {toggle(name, on) { on ? names.add(name) : names.delete(name); }},
    querySelector(selector) { return selector === '.compact-chat-send-icon' ? sendIcon : stopIcon; },
    setAttribute(name, value) { this[name] = value; }};
  context.window.CompactChat.setBusy(button, true, true);
  assert.equal(button.disabled, false);
  assert.equal(button['aria-label'], 'Arrêter la génération');
  assert.equal(stopIcon.hidden, false);
  assert.equal(names.has('is-busy'), true);
  context.window.CompactChat.setBusy(button, false);
  assert.equal(sendIcon.hidden, false);
  assert.equal(stopIcon.hidden, true);
  assert.equal(names.has('is-busy'), false);
});
