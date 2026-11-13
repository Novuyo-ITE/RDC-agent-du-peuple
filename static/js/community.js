(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  const state = {kind: 'all', page: 1, items: new Map(), selected: null, reply: null, before: null,
    feedRequest: null, threadRequest: null, submitting: false, lastFocus: null, messageMode: 'comment'};
  let discoveryTimer = null, discoveryChecks = 0;
  const csrf = () => document.querySelector('#community-post-form [name=csrfmiddlewaretoken]').value;
  const el = (tag, cls, content) => { const node = document.createElement(tag); if (cls) node.className = cls; if (content !== undefined) node.textContent = content; return node; };
  const safeUrl = value => { try { const url = new URL(value); return ['https:', 'http:'].includes(url.protocol) ? url.href : null; } catch { return null; } };
  const date = value => new Intl.DateTimeFormat('fr', {day:'numeric', month:'short', hour:'2-digit', minute:'2-digit'}).format(new Date(value));
  const status = (id, message, error = false) => { $(id).textContent = message; $(id).dataset.error = String(error); };
  function icon(name) {
    const node = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    node.setAttribute('viewBox', '0 0 24 24'); node.setAttribute('fill', 'none'); node.setAttribute('stroke', 'currentColor'); node.setAttribute('stroke-width', '1.6'); node.setAttribute('aria-hidden','true');
    const path = document.createElementNS(node.namespaceURI, 'path');
    path.setAttribute('d', name === 'heart' ? 'M20.8 4.6a5.5 5.5 0 0 0-7.8 0L12 5.7l-1.1-1.1a5.5 5.5 0 0 0-7.8 7.8L12 21l8.8-8.6a5.5 5.5 0 0 0 0-7.8Z' : 'M21 11.5a8.4 8.4 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.4 8.4 0 0 1-3.8-.9L3 21l1.9-5.7a8.4 8.4 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.4 8.4 0 0 1 3.8-.9h.5a8.5 8.5 0 0 1 8 8v.5Z'); node.append(path); return node;
  }
  async function api(path, data, signal) {
    let response;
    try { response = await fetch(path, {method: data === undefined ? 'GET' : 'POST', credentials: 'same-origin', signal,
      headers: data === undefined ? {} : {'Content-Type':'application/json', 'X-CSRFToken':csrf()},
      body: data === undefined ? undefined : JSON.stringify(data)}); }
    catch(error) { if(error.name === 'AbortError') throw error; throw new Error('Connexion au serveur interrompue. Vérifiez que Django est démarré, puis réessayez.'); }
    let result; try { result = await response.json(); } catch { throw new Error('Service indisponible. Réessayez dans un instant.'); }
    if (!response.ok) throw new Error(result.error || 'Impossible de terminer cette action.');
    return result;
  }
  const endpoint = (item, action) => `/api/community/${item.target}/${item.id}/${action}/`;
  function renderPost(item) {
    const fullTweet = item.kind === 'social' && item.platform === 'X / Twitter';
    const card = el('article', 'community-post'); card.dataset.key = item.key;
    const top = el('div', 'community-post-top'), avatar = el('span', 'community-avatar', item.kind === 'ai' ? '✦' : item.author.slice(0,2).toUpperCase());
    if (item.source_url && item.kind !== 'ai' && window.SourceBrand) avatar.replaceChildren(SourceBrand.createIcon(item.source_url,item.author));
    const identity = el('div'); identity.append(el('div','community-post-author',item.author), el('div','community-post-meta',(item.discovered_by ? 'Repéré via Tavily · ' : '') + date(item.date) + (item.region ? ' · ' + item.region : '')));
    const labels = {news:'Article de presse', community:'Communauté', social:item.platform + ' · partagé', ai:'✦ Généré par IA'};
    if(item.summary_ai) labels[item.kind]='✦ Résumé IA';
    top.append(avatar, identity, el('span','community-kind' + (item.kind === 'ai' ? ' community-kind-ai' : ''),labels[item.kind]));
    const heading = el('h2'), title = el('button','',item.title); title.type='button'; title.addEventListener('click',()=>openThread(item)); heading.append(title);
    const body = el('p','community-post-body'+(item.summary_ai||fullTweet?' is-expanded':''),item.body); card.append(top);if(!item.summary_ai&&!(fullTweet&&item.text_complete))card.append(heading);card.append(body);
    if(safeUrl(item.image)){const photo=el('a','community-news-photo');photo.href=item.article_url||safeUrl(item.source_url);if(!item.article_url){photo.target='_blank';photo.rel='noopener noreferrer';}photo.setAttribute('aria-label','Voir la publication complète : '+item.title);const img=el('img');img.src=item.image;img.alt=item.title;img.loading='lazy';img.referrerPolicy='no-referrer';img.addEventListener('error',()=>photo.hidden=true);photo.append(img);card.append(photo);}
    if(item.image&&safeUrl(item.image_article_url)){const credit=el('a','community-summary-note','Photo de l’article partagé ↗');credit.href=item.image_article_url;credit.target='_blank';credit.rel='noopener noreferrer';card.append(credit);}
    if (item.body.length > 240 && !item.summary_ai && !fullTweet) { const expand=el('button','community-expand','Développer l’extrait'); expand.type='button'; expand.setAttribute('aria-expanded','false'); expand.addEventListener('click',()=>{ const expanded=body.classList.toggle('is-expanded'); expand.textContent=expanded?'Réduire':'Développer l’extrait'; expand.setAttribute('aria-expanded',String(expanded)); }); card.append(expand); }
    if(item.summary_ai&&item.summary_basis==='stored_text')card.append(el('small','community-summary-note','Résumé fondé sur le texte enregistré ; page source inaccessible lors de la génération.'));
    const url=safeUrl(item.source_url);
    if (url) { const link=el('a','community-source-preview'); link.href=url; link.target='_blank'; link.rel='noopener noreferrer';
      const info=el('div'), sourceName=el('strong','source-identity'); if(window.SourceBrand)sourceName.append(SourceBrand.createIcon(url,item.source_host));sourceName.append(el('span','',item.source_host+' ↗')); info.append(sourceName,el('span','',item.text_complete?'Texte original du post X · voir la source':item.discovered_by?(item.excerpt_cleaned?'Extrait nettoyé · repéré via Tavily':'Extrait indexé via Tavily · contenu non vérifié'):item.kind==='social'?'Publication externe · contenu non vérifié':item.kind==='ai'?'Article à l’origine de ce décryptage':item.category_label||'Consulter la source originale')); link.append(info); card.append(link); }
    if(item.article_url){const read=el('a','community-read-original','Lire la publication complète ↗');read.href=item.article_url;card.append(read);}
    const actions=el('div','community-post-actions'), like=el('button'); like.type='button'; like.dataset.action='like'; like.setAttribute('aria-label','Aimer cette publication'); like.setAttribute('aria-pressed',String(item.liked)); like.append(icon('heart'),el('span','',String(item.likes)));
    like.addEventListener('click',async()=>{ like.disabled=true; try { const result=await api(endpoint(item,'like'),{liked:!item.liked}); item.likes=result.likes; item.liked=result.liked; like.setAttribute('aria-pressed',String(item.liked)); like.lastChild.textContent=String(item.likes); } catch(error){ status('community-feed-status',error.message,true); } finally{like.disabled=false;} });
    const comment=el('button'); comment.type='button'; comment.dataset.action='comments'; comment.append(icon('comments'),el('span','',`${item.comments} commentaire${item.comments===1?'':'s'}`)); comment.addEventListener('click',()=>openThread(item));
    const ai=el('button','community-ai-action','✦ Question à l’IA'); ai.type='button'; ai.addEventListener('click',()=>{openThread(item,'ai'); $('comment-body').focus();});
    actions.append(like,comment,ai); card.append(actions); return card;
  }
  async function loadFeed(more=false) {
    if(state.feedRequest) state.feedRequest.abort();
    const controller=new AbortController(); state.feedRequest=controller;
    const page=more?state.page+1:1, params=new URLSearchParams({kind:state.kind,page,q:$('community-query').value,category:$('community-category').value});
    $('community-feed').setAttribute('aria-busy','true'); $('community-more').disabled=true; status('community-feed-status','Chargement du fil…');
    try { const result=await api('/api/community/feed/?'+params,undefined,controller.signal);
      if(!more){$('community-feed').replaceChildren(); state.items.clear();}
      for(const item of result.items){if(!state.items.has(item.key)){$('community-feed').append(renderPost(item)); state.items.set(item.key,item);}}
      if(!state.items.size){const empty=el('div','community-empty'); empty.append(el('h2','','La conversation commence ici.'),el('p','',state.kind==='ai'?'Les décryptages apparaîtront après génération à partir des actualités. Vous pouvez déjà discuter des articles avec l’IA.':'Aucune publication pour ce filtre. Partagez un article, un lien social ou votre première question.')); $('community-feed').append(empty);}
      state.page=page; $('community-more').hidden=!result.has_more; status('community-feed-status',''); highlight();
      showDiscovery(result.discovery);
    }catch(error){if(error.name!=='AbortError'){status('community-feed-status',error.message,true); if(!state.items.size)$('community-feed').replaceChildren();}}
    finally{if(state.feedRequest===controller){$('community-feed').setAttribute('aria-busy','false'); $('community-more').disabled=false; state.feedRequest=null;}}
  }
  function showDiscovery(discovery) {
    const visible = ['all','social'].includes(state.kind);
    const messages = {refreshing:'Tavily recherche des publications sociales publiques…',
      unconfigured:'Recherche sociale inactive : la clé Tavily doit être configurée sur le serveur.',
      error:'Recherche sociale temporairement indisponible. Les publications déjà enregistrées restent accessibles.',
      partial:'Certaines sources sociales sont indisponibles. Les résultats trouvés ont été ajoutés.',
      ready:'Publications sociales repérées via Tavily · extraits indexés, couverture partielle.'};
    status('community-discovery-status', visible ? messages[discovery?.state] || '' : '');
    if (discovery?.state === 'refreshing' && !discoveryTimer && discoveryChecks < 32) {
      discoveryTimer = setTimeout(() => {
        discoveryTimer = null; discoveryChecks++;
        if (!document.hidden && !state.selected && !state.submitting && !state.feedRequest &&
            !document.activeElement?.matches('input,textarea,select') && state.page === 1) loadFeed();
      }, 5000);
    }
    if (discovery?.state !== 'refreshing') discoveryChecks = 0;
  }
  function highlight(){document.querySelectorAll('.community-post').forEach(card=>card.classList.toggle('is-active',card.dataset.key===state.selected?.key));}
  function setReply(comment){state.reply=comment; $('thread-reply').hidden=!comment; if(comment)$('thread-reply').querySelector('span').textContent=`En réponse à ${comment.author} · #${comment.id}`;}
  function renderComment(comment){const node=el('article','community-comment'+(comment.is_ai?' is-ai':''));node.dataset.id=comment.id;
    const meta=el('div','community-comment-meta');meta.append(el('strong','',comment.author),el('span','',date(comment.date))); if(comment.is_ai)meta.append(el('span','community-kind-ai','✦ Réponse IA'));
    node.append(meta);if(comment.parent)node.append(el('div','community-comment-parent',`En réponse au commentaire #${comment.parent}`));const content=el(comment.is_ai?'div':'p','',comment.body);if(comment.is_ai)ChatMarkdown.render(content,comment.body);node.append(content);
    const reply=el('button','','Répondre');reply.type='button';reply.addEventListener('click',()=>{setReply(comment);$('comment-body').focus();});node.append(reply);if(window.ChatCopy)ChatCopy.attach(node,comment.body,comment.is_ai?'assistant':'user');return node;}
  async function loadComments(older=false){const item=state.selected;if(!item)return;
    if(state.threadRequest)state.threadRequest.abort();const controller=new AbortController();state.threadRequest=controller;
    $('thread-log').setAttribute('aria-busy','true');
    try{const result=await api(endpoint(item,'comments')+(older?'?before='+state.before:''),undefined,controller.signal);if(state.selected?.key!==item.key)return;
      const nodes=result.comments.map(renderComment);if(older)$('thread-comments').prepend(...nodes);else $('thread-comments').replaceChildren(...nodes);
      if(!result.comments.length&&!older)$('thread-comments').append(el('p','community-empty','Soyez la première personne à ouvrir la discussion.'));
      state.before=result.before;$('thread-older').hidden=!result.has_more;if(!older)$('thread-log').scrollTop=$('thread-log').scrollHeight;
    }catch(error){if(error.name!=='AbortError'&&state.selected?.key===item.key)status('comment-status',error.message,true);}
    finally{if(state.threadRequest===controller){state.threadRequest=null;$('thread-log').setAttribute('aria-busy','false');}}
  }
  function setMessageMode(mode){if(state.submitting)return;state.messageMode=mode;const ai=mode==='ai';
    document.querySelectorAll('[data-message-mode]').forEach(button=>button.setAttribute('aria-pressed',String(button.dataset.messageMode===mode)));
    $('community-comment-form').classList.toggle('is-ai-mode',ai);
    $('comment-body').placeholder=ai?'Que souhaitez-vous comprendre à propos de cette publication ?':'Ajoutez votre regard à la conversation…';
    $('comment-body-label').textContent=ai?'Votre question à l’IA sur cette publication':'Votre commentaire public';
    $('comment-mode-help').textContent=ai?'L’IA répond à partir de cette publication. Votre question et sa réponse apparaîtront dans le fil public.':'Échangez avec la communauté. L’IA ne répond pas automatiquement.';
    const send=$('comment-submit'), label=ai?'Poser la question à l’IA':'Publier le commentaire';send.dataset.sendLabel=label;send.setAttribute('aria-label',label);send.title=label;}
  document.querySelectorAll('[data-message-mode]').forEach(button=>button.addEventListener('click',()=>setMessageMode(button.dataset.messageMode)));
  function openThread(item,mode='comment'){if(state.submitting&&state.selected?.key!==item.key){status('comment-status','Patientez jusqu’à la fin de l’envoi.');return;}
    setMessageMode(mode);
    if(state.selected?.key!==item.key){$('comment-body').value='';setReply(null);status('comment-status','');}
    state.lastFocus=document.activeElement;state.selected=item;state.before=null;$('community-aside-welcome').hidden=true;$('community-thread').hidden=false;$('community-aside').classList.add('thread-open');$('thread-title').textContent=item.title;
    const url=safeUrl(item.source_url);$('thread-source').hidden=!url;if(url){$('thread-source').href=url;$('thread-source').classList.add('source-identity');$('thread-source').replaceChildren();if(window.SourceBrand)$('thread-source').append(SourceBrand.createIcon(url,item.author));$('thread-source').append(document.createTextNode('Voir la source ↗'));}
    $('thread-read-article').hidden=!item.article_url;if(item.article_url)$('thread-read-article').href=item.article_url;
    const locationUrl=new URL(location.href);locationUrl.searchParams.set('thread',item.key);history.replaceState(null,'',locationUrl);highlight();loadComments();}
  function closeThread(){if(state.submitting){status('comment-status','Patientez jusqu’à la fin de l’envoi.');return;}if(state.threadRequest)state.threadRequest.abort();state.selected=null;setReply(null);$('community-thread').hidden=true;$('community-aside-welcome').hidden=false;$('community-aside').classList.remove('thread-open');const url=new URL(location.href);url.searchParams.delete('thread');history.replaceState(null,'',url);highlight();if(state.lastFocus?.isConnected)state.lastFocus.focus();}
  $('community-post-form').addEventListener('submit',async event=>{event.preventDefault();const form=event.currentTarget,button=form.querySelector('button[type=submit]');button.disabled=true;status('post-status','Publication en cours…');
    try{const data=Object.fromEntries(new FormData(form));delete data.csrfmiddlewaretoken;await api('/api/community/feed/',data);saveName(data.author);form.reset();$('community-compose').open=false;state.kind='all';document.querySelectorAll('[data-kind]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.kind==='all')));$('community-query').value='';$('community-category').value='';await loadFeed();status('community-feed-status','Votre publication est en ligne.');}catch(error){status('post-status',error.message,true);}finally{button.disabled=false;}});
  $('community-comment-form').addEventListener('submit',async event=>{event.preventDefault();if(state.submitting||!state.selected)return;
    const item=state.selected,body=$('comment-body').value.trim();if(!body)return;const ai=state.messageMode==='ai',author=$('comment-author').value.trim(),reply=state.reply;
    state.submitting=true;document.querySelectorAll('.community-comment-actions button').forEach(b=>b.disabled=true);CompactChat.setBusy($('comment-submit'),true);status('comment-status',ai?'L’IA prépare une réponse à partir du fil…':'Envoi du commentaire…');
    // A question is saved first so a failed AI request can be retried without duplicating it.
    let saved=null;
    try{saved=await api(endpoint(item,'comments'),{body,author,parent:reply?.id});$('comment-body').value='';setReply(null);item.comments++;saveName(author);await loadComments();
      if(ai){await api(endpoint(item,'ai'),{body,author,parent:saved.id});item.comments++;await loadComments();}status('comment-status','');
    }catch(error){status('comment-status',error.message,true);if(ai&&saved){const retry=el('button','community-ask-ai','Réessayer la réponse IA');retry.type='button';retry.addEventListener('click',async()=>{retry.disabled=true;try{await api(endpoint(item,'ai'),{body,author,parent:saved.id});item.comments++;await loadComments();status('comment-status','');}catch(err){status('comment-status',err.message,true);}finally{retry.disabled=false;}});$('comment-status').append(document.createElement('br'),retry);}}
    finally{state.submitting=false;document.querySelectorAll('.community-comment-actions button').forEach(b=>b.disabled=false);CompactChat.setBusy($('comment-submit'),false);document.querySelectorAll('.community-post').forEach(card=>{if(card.dataset.key===item.key){card.querySelector('[data-action=comments] span').textContent=`${item.comments} commentaire${item.comments===1?'':'s'}`;}});}});
  function saveName(name){if(!name)return;try{localStorage.setItem('community-display-name',name);}catch{}$('comment-author').value=name;$('community-post-form').elements.author.value=name;}
  try{const name=localStorage.getItem('community-display-name');if(name)saveName(name);}catch{}
  document.querySelectorAll('[data-kind]').forEach(button=>button.addEventListener('click',()=>{state.kind=button.dataset.kind;document.querySelectorAll('[data-kind]').forEach(b=>b.setAttribute('aria-pressed',String(b===button)));loadFeed();}));
  $('community-search').addEventListener('submit',event=>{event.preventDefault();loadFeed();});$('community-category').addEventListener('change',()=>loadFeed());$('community-more').addEventListener('click',()=>loadFeed(true));$('community-refresh').addEventListener('click',()=>loadFeed());$('thread-refresh').addEventListener('click',()=>loadComments());$('thread-older').addEventListener('click',()=>loadComments(true));$('thread-close').addEventListener('click',closeThread);$('thread-reply').querySelector('button').addEventListener('click',()=>setReply(null));
  document.addEventListener('keydown',event=>{if(event.key==='Escape'&&state.selected)closeThread();});
  loadFeed().then(async()=>{const key=new URL(location.href).searchParams.get('thread');if(!key)return;if(state.items.has(key)){openThread(state.items.get(key));return;}if(!/^(news|post):\d+$/.test(key))return;
    // Deep links outside the first feed page still have a useful direct discussion view.
    const [target,id]=key.split(':');try{const result=await api(`/api/community/${target}/${id}/comments/`);openThread({key,target,id,title:result.title,source_url:result.source_url,article_url:result.article_url,comments:result.count});}catch(error){status('community-feed-status',error.message,true);}});
})();
