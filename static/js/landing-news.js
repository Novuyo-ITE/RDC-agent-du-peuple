/* Warm news images before the reader reaches the section, including hidden slides. */
(() => {
    'use strict';
    const section = document.getElementById('actualites');
    if (!section) return;
    const images = [...section.querySelectorAll('img')];
    function load() {
        images.forEach(img => {
            img.loading = 'eager';
            // Hidden carousel slides do not reliably load lazy images until shown.
            if (img.closest('.headline-slide') && img.getAttribute('src')) {
                const preload = new Image();
                preload.src = img.src;
            }
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
    function initializeCarousel() {
            // Headline News Carousel Controller (matching platform news carousels)
            const slides = document.querySelectorAll('.headline-slide');
            const prevBtn = document.getElementById('headline-prev-btn');
            const nextBtn = document.getElementById('headline-next-btn');
            const counter = document.getElementById('headline-slide-indicator');
            let currentSlide = 0;
            let slideInterval = null;

            function showSlide(index) {
                if (!slides || slides.length === 0) return;
                slides.forEach((s, i) => {
                    s.classList.toggle('hidden', i !== index);
                });
                currentSlide = index;
                if (counter) {
                    counter.textContent = `${currentSlide + 1} / ${slides.length}`;
                }
            }

            function nextSlide() {
                if (!slides || slides.length === 0) return;
                showSlide((currentSlide + 1) % slides.length);
            }

            function prevSlide() {
                if (!slides || slides.length === 0) return;
                showSlide((currentSlide - 1 + slides.length) % slides.length);
            }

            if (nextBtn) nextBtn.addEventListener('click', () => { nextSlide(); resetTimer(); });
            if (prevBtn) prevBtn.addEventListener('click', () => { prevSlide(); resetTimer(); });

            function startTimer() {
                if (slides && slides.length > 1) {
                    slideInterval = setInterval(nextSlide, 7000);
                }
            }

            function resetTimer() {
                if (slideInterval) clearInterval(slideInterval);
                startTimer();
            }

            const carouselCard = document.getElementById('headline-carousel-card');
            if (carouselCard) {
                carouselCard.addEventListener('mouseenter', () => { if (slideInterval) clearInterval(slideInterval); });
                carouselCard.addEventListener('mouseleave', () => { startTimer(); });
            }
            startTimer();
    }
    initializeCarousel();
    if (document.querySelector('#actualites .headline-slide')) return;
    // Empty production databases need time for the background RSS import.
    let attempts = 0;
    async function checkFeed() {
        if (document.hidden) { window.setTimeout(checkFeed, 15000); return; }
        attempts++;
        try {
            const response = await fetch(window.location.pathname, {
                headers: {'X-Requested-With': 'XMLHttpRequest'},
                cache: 'no-store', signal: AbortSignal.timeout(10000)
            });
            if (response.ok) {
                const page = new DOMParser().parseFromString(await response.text(), 'text/html');
                const fresh = page.querySelector('#actualites');
                if (fresh && fresh.querySelector('.headline-slide')) {
                    document.getElementById('actualites').replaceWith(fresh);
                    fresh.querySelectorAll('img').forEach(img => { img.loading = 'eager'; });
                    if (window.lucide) window.lucide.createIcons();
                    initializeCarousel();
                    return;
                }
            }
        } catch (_) { /* Keep the rest of the landing page usable if refresh fails. */ }
        if (attempts < 6) window.setTimeout(checkFeed, 15000);
    }
    window.setTimeout(checkFeed, 10000);
})();
