const {test} = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const path = require('node:path');
const template = fs.readFileSync(path.join(__dirname, '../templates/index.html'), 'utf8');

test('Streaming render integrates available photographs before the answer is finished', () => {
  const start = template.indexOf('    function renderMainAnswer(');
  const end = template.indexOf('    async function submitQuery()', start);
  const calls = [];
  const answerText = {};
  const context = {window:{ChatMarkdown:true}, ChatMarkdown:{render(node,text){assert.equal(node,answerText);calls.push(text);}},
    splitAnswerLists(){}, integrateArticlePhotos(node,sources){calls.push(sources);}, console};
  vm.createContext(context); vm.runInContext(template.slice(start,end),context);
  const sources = [{url:'https://example.cd/news',image_url:'https://example.cd/photo.jpg'}];
  context.renderMainAnswer({classList:{add(){}},querySelector(){return answerText;}}, 'First words and a citation', sources);
  assert.deepEqual(calls, ['First words and a citation', sources]);
});

test('Each cited story receives its own image while streaming; unmatched or imageless text receives none', () => {
  const start=template.indexOf('    function integrateArticlePhotos(');
  const end=template.indexOf('    function createDistinctSourcesWidget(',start);
  const placed=[];let images=0, removals=0, gallery=null;
  const first={style:{},querySelectorAll(){return [{href:'https://example.cd/one'}];}};
  const second={style:{},querySelectorAll(){return [{href:'https://example.cd/two'}];}};
  const noPhoto={style:{},querySelectorAll(){return [{href:'https://example.cd/three'}];}};
  const answerText={children:[first],after(element){gallery=element;}};
  const root={querySelector(selector){return selector==='.chat-answer-text'?answerText:gallery;}};
  const context={URL,Map,Set,Date,Intl,window:{},document:{
    createElement(tag){
      if(tag==='img')images++;
      return {style:{},append(child){if(this.className==='chat-source-gallery')placed.push(child);},setAttribute(){},addEventListener(){},remove(){removals++;}};
    },
    createTextNode(text){return {textContent:text};}
  }};
  vm.createContext(context);vm.runInContext(template.slice(start,end),context);
  const sources=[
    {url:'https://example.cd/one',image_url:'https://example.cd/one.jpg',title:'Premier article',reference_only:true},
    {url:'https://example.cd/two',image_url:'https://example.cd/two.jpg',title:'Deuxième article',reference_only:true},
    {url:'https://example.cd/three',title:'Sans photo',reference_only:true}
  ];
  context.integrateArticlePhotos(root,sources);
  context.integrateArticlePhotos(root,sources);
  assert.equal(images,1);
  assert.equal(placed.length,1);
  assert.equal(placed[0].style.order,'1');
  answerText.children.push(second,noPhoto);
  context.integrateArticlePhotos(root,sources);
  assert.equal(images,2);
  assert.equal(placed.length,2);
  assert.equal(first.style.order,'0');
  assert.equal(second.style.order,'2');
  assert.equal(placed[1].style.order,'3');
  assert.equal(removals,0);
  const finalSources=context.mergeDisplayedSources(root,[]);
  assert.equal(finalSources.length,2);
  assert.equal(finalSources[0].url,sources[0].url);
  assert.equal(finalSources[0].reference_only,true);
  const cited=context.mergeDisplayedSources(root,[{url:sources[0].url,title:'Article cité'}]);
  assert.equal(cited.length,2);
  assert.equal(cited[0].image_url,sources[0].image_url);
  assert.equal(cited[0].reference_only,undefined);
  context.integrateArticlePhotos(root,finalSources);
  assert.equal(placed.length,2);
  assert.equal(removals,0);
});

test('Creating the live answer bubble needs no sources and cannot block the request', () => {
  const start = template.indexOf('    function appendAssistantStreamContainer(id)');
  const end = template.indexOf('    function appendFinishedAssistantMessage(', start);
  let inserted = '', refreshed = false;
  const context = {
    document: {getElementById(id) {
      assert.equal(id, 'chat-messages');
      return {insertAdjacentHTML(position, html) {inserted = html;}};
    }},
    refreshIcons() {refreshed = true;},
  };
  vm.createContext(context);
  vm.runInContext(template.slice(start, end), context);
  assert.doesNotThrow(() => context.appendAssistantStreamContainer('answer-test'));
  assert.match(inserted, /id="answer-test"/);
  assert.match(inserted, /id="loader-answer-test"/);
  assert.ok(refreshed);
});

test('send button shows thinking and writing, then stops the current stream', async () => {
  const start = template.indexOf('    function setChatResponseStatus(');
  const end = template.indexOf('    // USER MESSAGE:', start);
  const classes = new Set(), sendIcon = {hidden: false}, stopIcon = {hidden: true};
  const button = {classList: {toggle(name, on) { on ? classes.add(name) : classes.delete(name); }},
    querySelector(selector) { return selector === '.chat-send-icon' ? sendIcon : stopIcon; },
    setAttribute(name, value) { this[name] = value; }};
  const label = {textContent: ''}, status = {hidden: true, querySelector() { return label; }};
  const input = {value: 'Bonjour'}, container = {scrollTop: 0, scrollHeight: 0};
  const answer = {messages: [], append(message) { this.messages.push(message); }};
  let responseId, resolveResponse, resolveToken, signal, fetches = 0;
  const responseReady = new Promise(resolve => { resolveResponse = resolve; });
  const tokenRendered = new Promise(resolve => { resolveToken = resolve; });
  let reads = 0;
  const context = {
    document: {getElementById(id) {
      if (id === 'send-btn') return button;
      if (id === 'chat-response-status') return status;
      if (id === 'query-input') return input;
      if (id === 'chat-messages') return container;
      if (id === responseId) return answer;
      return null;
    }, createElement() { return {}; }, querySelector() { return null; }},
    window: {currentSessionId: 'test'}, sessionStorage: {setItem() {}},
    rememberChatSession() {}, appendUserMessage() {},
    appendAssistantStreamContainer(id) { responseId = id; },
    renderMainAnswer(node, text) { assert.equal(text, 'Réponse partielle'); resolveToken(); },
    refreshIcons() {}, getCookie() { return ''; },
    fetch(url, options) { fetches++; signal = options.signal; return responseReady; },
    AbortController, TextDecoder, TextEncoder, setTimeout, clearTimeout, console,
  };
  vm.createContext(context);
  vm.runInContext("let chatBusy=false, historyLoading=false, activeChatRequest=null, mainHistory=[]; let currentLanguage='fr';\n" + template.slice(start, end), context);
  const request = context.submitQuery();
  assert.equal(label.textContent, 'Réflexion en cours');
  assert.equal(status.hidden, false);
  assert.equal(classes.has('is-generating'), true);
  assert.equal(sendIcon.hidden, true);
  assert.equal(stopIcon.hidden, false);
  assert.equal(button['aria-label'], 'Arrêter la génération');
  input.value = 'Une autre question';
  await context.submitQuery();
  assert.equal(fetches, 1);
  resolveResponse({ok: true, body: {getReader() { return {read() {
    if (!reads++) return Promise.resolve({done: false, value: new TextEncoder().encode('data: {"type":"token","token":"Réponse partielle"}\n\n')});
    return new Promise((resolve, reject) => signal.addEventListener('abort', () => reject(Object.assign(new Error('stopped'), {name: 'AbortError'}))));
  }}; }}});
  await tokenRendered;
  assert.equal(label.textContent, 'Rédaction de la réponse');
  context.handleSendAction();
  await request;
  assert.equal(signal.aborted, true);
  assert.equal(answer.messages[0].textContent, 'Génération arrêtée.');
  assert.equal(status.hidden, true);
  assert.equal(classes.has('is-generating'), false);
  assert.equal(sendIcon.hidden, false);
  assert.equal(stopIcon.hidden, true);
  assert.equal(button['aria-label'], 'Envoyer la question');
});
