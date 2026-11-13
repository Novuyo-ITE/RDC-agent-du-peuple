(() => {
    const carousel = document.querySelector('[data-service-carousel]');
    if (!carousel) return;
    const slides = [...carousel.querySelectorAll('[data-service-slide]')];
    if (slides.length < 2) return;
    const toggles = [...carousel.querySelectorAll('[data-service-carousel-action="toggle"]')];
    const motion = window.matchMedia('(prefers-reduced-motion: reduce)');
    let current = 0, paused = motion.matches, mouseInside = false, gesture = null, suppressClick = false;

    function show(index) {
        current = (index + slides.length) % slides.length;
        slides.forEach((slide, i) => { slide.hidden = i !== current; });
        toggles.forEach(toggle => {
            const label = paused ? 'Reprendre le défilement' : 'Mettre en pause';
            toggle.setAttribute('aria-label', label);
            toggle.setAttribute('title', label);
            toggle.setAttribute('aria-pressed', String(paused));
        });
    }
    carousel.addEventListener('click', event => {
        if (suppressClick) { event.preventDefault(); suppressClick = false; return; }
        const button = event.target.closest('[data-service-carousel-action]');
        if (!button) return;
        const action = button.dataset.serviceCarouselAction;
        if (action === 'previous' || action === 'next') {
            show(current + (action === 'next' ? 1 : -1));
            slides[current].querySelector(`[data-service-carousel-action="${action}"]`)?.focus();
        }
        if (action === 'toggle') { paused = !paused; show(current); }
    }, true);
    carousel.addEventListener('pointerenter', event => { if (event.pointerType === 'mouse') mouseInside = true; });
    carousel.addEventListener('pointerleave', event => { if (event.pointerType === 'mouse') mouseInside = false; });
    carousel.addEventListener('pointerdown', event => {
        if (event.pointerType === 'touch' || event.pointerType === 'pen') gesture = {x:event.clientX, y:event.clientY};
    });
    carousel.addEventListener('pointerup', event => {
        if (!gesture) return;
        const dx = event.clientX - gesture.x, dy = event.clientY - gesture.y;
        gesture = null;
        if (Math.abs(dx) < 45 || Math.abs(dx) <= Math.abs(dy)) return;
        show(current + (dx < 0 ? 1 : -1));
        suppressClick = true;
        window.setTimeout(() => { suppressClick = false; }, 500);
    });
    carousel.addEventListener('pointercancel', () => { gesture = null; });
    if (motion.addEventListener) motion.addEventListener('change', () => { if (motion.matches) { paused = true; show(current); } });
    show(0);
    window.setInterval(() => {
        if (!paused && !document.hidden && !mouseInside && !carousel.contains(document.activeElement)) show(current + 1);
    }, 8000);
})();
