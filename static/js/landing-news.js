/* Warm news images before the reader reaches the section, on the landing page. */
(() => {
    'use strict';
    const section = document.getElementById('actualites');
    if (!section) return;
    const images = [...section.querySelectorAll('img')];
    function load() {
        images.forEach(img => {
            img.loading = 'eager';
        });
    }
    if (!('IntersectionObserver' in window)) { load(); return; }
    const observer = new IntersectionObserver(entries => {
        if (!entries.some(entry => entry.isIntersecting)) return;
        load(); observer.disconnect();
    }, {rootMargin: '1000px 0px'});
    observer.observe(section);
})();

(() => {
    'use strict';
    const grid = document.getElementById('civia-landing-news-grid');
    if (!grid || grid.querySelector('article')) return;
    // Empty production databases need time for the background RSS import.
    let attempts = 0;
    async function checkFeed() {
        if (document.hidden) { window.setTimeout(checkFeed, 15000); return; }
        attempts++;
        try {
            const response = await fetch(window.location.pathname + window.location.search, {
                headers: {'X-Requested-With': 'XMLHttpRequest'},
                cache: 'no-store', signal: AbortSignal.timeout(10000)
            });
            if (response.ok) {
                const page = new DOMParser().parseFromString(await response.text(), 'text/html');
                const fresh = page.getElementById('civia-landing-news-grid');
                if (fresh && fresh.querySelector('article')) {
                    grid.replaceWith(fresh);
                    fresh.querySelectorAll('img').forEach(img => { img.loading = 'eager'; });
                    if (window.lucide) window.lucide.createIcons();
                    return;
                }
            }
        } catch (_) { /* Keep the rest of the landing page usable if refresh fails. */ }
        if (attempts < 6) window.setTimeout(checkFeed, 15000);
    }
    window.setTimeout(checkFeed, 10000);
})();
