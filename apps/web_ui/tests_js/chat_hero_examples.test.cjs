const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const source = fs.readFileSync(path.join(__dirname, '../../../static/js/chat-hero-examples.js'), 'utf8');

function fixture(reducedMotion = false) {
  let target = {textContent: '', isConnected: true, dataset: {}}, mutationCallback, motionCallback, nextId = 0;
  const scheduled = new Map();
  const motion = {matches: reducedMotion, addEventListener(type, fn) { motionCallback = fn; }};
  const container = {querySelector: () => target};
  const document = {hidden: false, getElementById: () => container};
  const window = {matchMedia: () => motion,
    setTimeout(fn) { const id = ++nextId; scheduled.set(id, fn); return id; },
    clearTimeout(id) { scheduled.delete(id); }};
  class MutationObserver { constructor(fn) { mutationCallback = fn; } observe() {} }
  vm.runInNewContext(source, {window, document, MutationObserver});
  return {document, motion, scheduled, get target() { return target; },
    tick() { const [id, fn] = scheduled.entries().next().value; scheduled.delete(id); fn(); },
    replace() { target.isConnected = false; target = {textContent: '', isConnected: true, dataset: {}}; mutationCallback(); },
    remove() { target.isConnected = false; target = null; mutationCallback(); },
    motionChange(value) { motion.matches = value; motionCallback(); }};
}

test('types and erases five different examples and restarts on a new chat', () => {
  const item = fixture();
  const completed = new Set([item.target.textContent]);
  const colors = [item.target.dataset.color];
  for (let i = 0; i < 500; i++) {
    item.tick();
    if (colors[colors.length - 1] !== item.target.dataset.color) colors.push(item.target.dataset.color);
    if (item.target.textContent.endsWith('?')) completed.add(item.target.textContent);
  }
  assert.equal(completed.size, 5);
  assert.ok([...completed].some(text => text.includes('guerre')));
  assert.ok([...completed].some(text => text.includes('passeport')));
  assert.deepEqual(colors.slice(0, 6), ['blue', 'red', 'yellow', 'blue', 'red', 'yellow']);
  item.replace();
  assert.equal(item.target.textContent, 'Besoin d’un passeport biométrique ?');
  assert.equal(item.scheduled.size, 1);
  item.remove();
  assert.equal(item.scheduled.size, 0);
});

test('respects reduced motion and suspends typing in a hidden tab', () => {
  const item = fixture(true);
  assert.equal(item.scheduled.size, 0);
  item.motionChange(false);
  assert.equal(item.scheduled.size, 1);
  const before = item.target.textContent;
  item.document.hidden = true;
  item.tick();
  assert.equal(item.target.textContent, before);
  item.document.hidden = false;
  item.tick();
  assert.notEqual(item.target.textContent, before);
  item.motionChange(true);
  assert.equal(item.scheduled.size, 0);
});
