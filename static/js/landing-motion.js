(() => {
    'use strict';
    const reduced = window.matchMedia('(prefers-reduced-motion: reduce)');
    const cards = document.querySelectorAll('#branches-secteurs .group');
    cards.forEach(card => card.classList.add('landing-sector-card'));
    if (!('IntersectionObserver' in window) || reduced.matches) return;
    const targets = document.querySelectorAll('section > .max-w-7xl > div, #branches-secteurs .landing-sector-card');
    const observer = new IntersectionObserver(entries => {
        entries.forEach(entry => {
            if (!entry.isIntersecting) return;
            entry.target.classList.remove('is-pending');
            entry.target.classList.add('is-visible');
            observer.unobserve(entry.target);
        });
    }, {threshold: 0.06});
    targets.forEach((target, index) => {
        // News must remain readable while remote photographs are loading.
        if (target.closest('#actualites')) return;
        target.classList.add('landing-reveal');
        if (target.getBoundingClientRect().top < window.innerHeight) return;
        target.style.setProperty('--reveal-delay', `${(index % 3) * 70}ms`);
        target.classList.add('is-pending');
        observer.observe(target);
    });
    reduced.addEventListener('change', () => {
        if (!reduced.matches) return;
        observer.disconnect();
        targets.forEach(target => target.classList.remove('is-pending'));
    });
})();
