const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const source = fs.readFileSync(path.join(__dirname, '../../../static/js/service-news-carousel.js'), 'utf8');

function carouselFixture(reducedMotion = false) {
  const slides = [0, 1, 2].map(i => ({hidden: i !== 0, querySelector: () => ({focus() {}})}));
  const attributes = [{}, {}, {}];
  const toggles = attributes.map(attrs => ({setAttribute(key, value) { attrs[key] = value; }}));
  const handlers = {};
  let timer;
  const carousel = {
    querySelectorAll: selector => selector.includes('slide') ? slides : toggles,
    addEventListener: (type, fn) => { handlers[type] = fn; },
    contains: target => target === 'focus',
  };
  const document = {querySelector: () => carousel, hidden: false, activeElement: null};
  const window = {matchMedia: () => ({matches: reducedMotion, addEventListener() {}}),
    setInterval: fn => { timer = fn; }, setTimeout() {}};
  vm.runInNewContext(source, {document, window});
  return {
    slides, attributes, handlers, document, tick: () => timer(),
    current() { return slides.findIndex(slide => !slide.hidden); },
    click(action) {
      handlers.click({target: {closest: () => ({dataset: {serviceCarouselAction: action}})}, preventDefault() {}});
    },
  };
}

test('rotates, wraps, pauses and respects focus', () => {
  const item = carouselFixture();
  item.tick(); assert.equal(item.current(), 1);
  item.tick(); item.tick(); assert.equal(item.current(), 0);
  item.click('previous'); assert.equal(item.current(), 2);
  item.click('toggle'); item.tick(); assert.equal(item.current(), 2);
  assert.equal(item.attributes[2]['aria-label'], 'Reprendre le défilement');
  item.click('toggle'); item.document.activeElement = 'focus'; item.tick();
  assert.equal(item.current(), 2);
});

test('supports swiping and starts paused for reduced motion', () => {
  const item = carouselFixture(true);
  item.tick(); assert.equal(item.current(), 0);
  assert.equal(item.attributes[0]['aria-label'], 'Reprendre le défilement');
  item.handlers.pointerdown({pointerType: 'touch', clientX: 150, clientY: 20});
  item.handlers.pointerup({clientX: 70, clientY: 25});
  assert.equal(item.current(), 1);
  let prevented = false;
  item.handlers.click({preventDefault() { prevented = true; }});
  assert.equal(prevented, true);
});
