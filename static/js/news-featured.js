/* Rotate only the current filtered edition; its regular refresh remains separate. */
(() => {
  const motion = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)');
  let paused = Boolean(motion && motion.matches);
  const lead = () => document.querySelector('#news-live-content .edition-lead');
  const slides = element => element ? [...element.querySelectorAll('.edition-lead-slide')] : [];

  function capture() {
    const items = slides(lead());
    return {active:items.find(item => !item.hidden)?.dataset.featuredId, newest:items[0]?.dataset.featuredId};
  }
  function show(index) {
    const element = lead(), items = slides(element);
    if (!items.length) return;
    const selected = ((index % items.length) + items.length) % items.length;
    items.forEach((item, i) => { item.hidden = i !== selected; });
    const position = element.querySelector('[data-featured-position]');
    if (position) position.textContent = `${selected + 1} / ${items.length}`;
    const toggle = element.querySelector('[data-featured-action="toggle"]');
    if (toggle) { toggle.textContent = paused ? 'Reprendre' : 'Mettre en pause'; toggle.setAttribute('aria-pressed', String(paused)); }
  }
  function restore(previous) {
    const items = slides(lead());
    let index = 0;
    if (previous && items[0]?.dataset.featuredId === previous.newest) {
      const found = items.findIndex(item => item.dataset.featuredId === previous.active);
      if (found >= 0) index = found;
    }
    show(index);
  }
  function advance(amount) {
    const items = slides(lead());
    if (items.length < 2) return;
    const current = items.findIndex(item => !item.hidden);
    show((current < 0 ? 0 : current) + amount);
  }
  function tick() {
    const element = lead();
    if (!element || paused || document.hidden || document.querySelector('#news-article-modal:not([hidden])') ||
        element.contains(document.activeElement) || element.matches(':hover')) return;
    advance(1);
  }
  document.addEventListener('click', event => {
    const button = event.target.closest('[data-featured-action]');
    if (!button || !lead()?.contains(button)) return;
    const action = button.dataset.featuredAction;
    if (action === 'toggle') { paused = !paused; show(slides(lead()).findIndex(item => !item.hidden)); }
    if (action === 'previous') advance(-1);
    if (action === 'next') advance(1);
  });
  document.addEventListener('DOMContentLoaded', () => restore());
  window.FeaturedNews = {capture, restore};
  window.setInterval(tick, 9000);
})();
