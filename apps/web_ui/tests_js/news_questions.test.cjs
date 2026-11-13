const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const template = fs.readFileSync(path.join(__dirname, '../templates/news.html'), 'utf8');

test('generated suggestions populate the selected article and do not leak across articles', async () => {
  const start = template.indexOf('async function loadArticleSuggestions(');
  const end = template.indexOf('function showArticleChatWelcome(', start);
  let resolveFetch, displayed = null;
  const pending = new Promise(resolve => { resolveFetch = resolve; });
  const context = {
    AbortController, console,
    document: {querySelector(selector) { return selector.includes('csrfmiddlewaretoken') ? {value: 'token'} : {}; }},
    localStorage: {getItem() { return 'fr'; }},
    renderArticleQuestions(questions) { displayed = questions; },
    fetch: () => pending,
  };
  vm.createContext(context);
  vm.runInContext("let selectedArticleId='7', articleSuggestionsRequest=null, articleSuggestedQuestions=null;\n" + template.slice(start, end), context);
  const first = context.loadArticleSuggestions('7');
  vm.runInContext("selectedArticleId='8'; articleSuggestionsRequest=null;", context);
  resolveFetch({ok: true, json: async () => ({questions: ['Question de l’article 7 ?']})});
  await first;
  assert.equal(displayed, null);

  context.fetch = async () => ({ok: true, json: async () => ({questions: ['Question sur l’article 8 ?']})});
  await context.loadArticleSuggestions('8');
  assert.deepEqual(Array.from(displayed), ['Question sur l’article 8 ?']);
});

test('selecting a suggested question places it in the input without submitting it', () => {
  const start = template.indexOf('function renderArticleQuestions(');
  const end = template.indexOf('async function loadArticleSuggestions(', start);
  const buttons = [], input = {value: '', focus() { this.focused = true; }};
  const prompts = {replaceChildren() { buttons.length = 0; }, append(button) { buttons.push(button); }};
  const context = {document: {
    querySelector() { return prompts; },
    getElementById() { return input; },
    createElement() { return {addEventListener(type, callback) { this.click = callback; }}; },
  }};
  vm.runInNewContext(template.slice(start, end), context);
  context.renderArticleQuestions(['Pourquoi ce pont a-t-il ouvert ?']);
  buttons[0].click();
  assert.equal(input.value, 'Pourquoi ce pont a-t-il ouvert ?');
  assert.equal(input.focused, true);
});
