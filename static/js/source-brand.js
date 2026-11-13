/* Shared source identity: favicon first, persistent monogram when unavailable. */
(() => {
  'use strict';
  const escape = value => value.replace(/[<>&"']/g, c => ({'<':'&lt;','>':'&gt;','&':'&amp;','"':'&quot;',"'":'&apos;'}[c]));
  function load(image, sourceUrl, label = '') {
    let url; try { url = new URL(sourceUrl); if (!['http:','https:'].includes(url.protocol)) return; } catch { return; }
    const letters = escape((label || url.hostname.replace(/^www\./,'')).slice(0,2).toUpperCase());
    const fallback = 'data:image/svg+xml,' + encodeURIComponent(`<svg xmlns="http://www.w3.org/2000/svg" width="32" height="32" viewBox="0 0 32 32"><rect width="32" height="32" rx="7" fill="#e8f0f5"/><text x="16" y="21" text-anchor="middle" font-family="Arial,sans-serif" font-weight="700" font-size="12" fill="#285170">${letters}</text></svg>`);
    image.hidden = false; image.src = fallback; image.alt = ''; image.width = 16; image.height = 16;
    image.classList.add('source-icon'); image.referrerPolicy = 'no-referrer'; image.onerror = () => {image.onerror = null; image.src = fallback; image.hidden = false;};
    const requested = sourceUrl; image.dataset.sourceRequested = requested;
    const probe = new Image(); probe.referrerPolicy = 'no-referrer'; let second = false;
    probe.onload = () => { if (image.dataset.sourceRequested === requested) { image.hidden = false; image.src = probe.src; } };
    probe.onerror = () => { if (!second) { second = true; probe.src = 'https://www.google.com/s2/favicons?domain_url=' + encodeURIComponent(url.origin) + '&sz=32'; } };
    probe.src = url.origin + '/favicon.ico';
  }
  function createIcon(url, label) { const image = document.createElement('img'); load(image,url,label); return image; }
  function hydrate(root=document) { root.querySelectorAll('[data-source-favicon]').forEach(image => load(image,image.dataset.sourceFavicon,image.dataset.sourceName || '')); }
  window.SourceBrand = {load,createIcon,hydrate};
  hydrate();
})();
