const {test} = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const path = require('node:path');

test('Source previews retain attribution, use text safely, and omit invalid links', () => {
  const source = fs.readFileSync(path.join(__dirname, '../../../static/js/source-briefs.js'), 'utf8');
  function node(tag) {
    return {tag, children:[], setAttribute(){}, append(...items){this.children.push(...items);}};
  }
  const context = {URL, Set, document:{createElement:node}, window:{}};
  vm.createContext(context);
  vm.runInContext(source, context);
  const cards = context.window.SourceBriefs.create([
    {title:'Article', url:'https://example.cd/article', excerpt:'<img src=x onerror=alert(1)>', excerpt_label:'Extrait indexé'},
    {title:'Lien dangereux', url:'javascript:alert(1)', excerpt:'Texte'},
    {title:'Sans texte', url:'https://example.cd/unavailable'},
  ]);
  assert.equal(cards.children.length, 2);
  assert.equal(cards.children[0].children[0].href, 'https://example.cd/article');
  assert.equal(cards.children[0].children[2].textContent, '<img src=x onerror=alert(1)>');
  assert.equal(cards.children[1].children[1].textContent, 'Contenu de la page non disponible');
});
