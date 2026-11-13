/* One safe Markdown renderer for live responses and saved conversations. */
(() => {
  const allowed = new Set('P BR H1 H2 H3 H4 H5 H6 UL OL LI STRONG EM DEL BLOCKQUOTE PRE CODE A HR TABLE THEAD TBODY TR TH TD'.split(' '));
  function html(text) {
    const template = document.createElement('template');
    template.innerHTML = marked.parse(String(text), {gfm:true, breaks:false});
    function clean(parent) {
      for (const node of [...parent.childNodes]) {
        if (node.nodeType === 8) { node.remove(); continue; }
        if (node.nodeType !== 1) continue;
        if (!allowed.has(node.tagName)) { node.replaceWith(document.createTextNode(node.textContent)); continue; }
        const href = node.getAttribute('href'), start = node.getAttribute('start');
        for (const attr of [...node.attributes]) node.removeAttribute(attr.name);
        if (node.tagName === 'A' && href) {
          try { const url = new URL(href, location.origin); if (['http:','https:'].includes(url.protocol)) {
            node.href=url.href; node.target='_blank'; node.rel='noopener noreferrer';
          } } catch {}
        }
        if (node.tagName === 'OL' && /^\d+$/.test(start || '')) node.setAttribute('start',start);
        clean(node);
      }
    }
    clean(template.content); return template.innerHTML;
  }
  window.ChatMarkdown = {html, render(node,text) { node.classList.add('chat-markdown'); node.innerHTML=html(text); }};
})();
