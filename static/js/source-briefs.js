/* Source cards display attributed passages, not invented summaries. */
(() => {
  function create(sources) {
    const container = document.createElement('section');
    container.className = 'source-briefs';
    container.setAttribute('aria-label', 'Aperçus des sources');
    const seen = new Set();
    for (const source of sources || []) {
      let url;
      try { url = new URL(source.url); } catch { continue; }
      if (!['http:', 'https:'].includes(url.protocol) || seen.has(url.href)) continue;
      seen.add(url.href);
      const card = document.createElement('article'); card.className = 'source-brief';
      const link = document.createElement('a'); link.href = url.href; link.target = '_blank';
      link.rel = 'noopener noreferrer'; link.className = 'source-brief-link';
      if (window.SourceBrand) link.append(SourceBrand.createIcon(url.href, source.title || url.hostname));
      const name = document.createElement('span'); name.textContent = source.title || url.hostname;
      link.append(name); card.append(link);
      const label = document.createElement('div'); label.className = 'source-brief-label';
      label.textContent = source.excerpt ? (source.excerpt_label || 'Extrait de la source') : 'Contenu de la page non disponible';
      if (source.published_at) {
        const published = new Date(source.published_at);
        if (!Number.isNaN(published.getTime())) label.textContent += ' · Publié le ' + new Intl.DateTimeFormat('fr', {day:'numeric', month:'long', year:'numeric'}).format(published);
      }
      card.append(label);
      if (source.excerpt) {
        const excerpt = document.createElement('p'); excerpt.className = 'source-brief-excerpt';
        excerpt.textContent = source.excerpt; card.append(excerpt);
      }
      container.append(card);
    }
    return container;
  }
  window.SourceBriefs = {create};
})();
