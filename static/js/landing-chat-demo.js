(() => {
    'use strict';
    const container = document.getElementById('hero-chat-container');
    if (!container) return;
    const get = id => document.getElementById(`hero-demo-${id}`);
    const user = get('user'), question = get('question'), assistant = get('assistant');
    const thinking = get('thinking'), answer = get('answer'), status = get('status');
    const composer = get('composer'), toggle = document.getElementById('hero-chat-toggle');
    const next = get('next'), resource = get('resource');
    const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)');
    const payload = document.getElementById('hero-service-examples');
    let examples = [];
    try { examples = JSON.parse(payload ? payload.textContent : '[]'); } catch (_) {}
    if (!examples.length) {
        status.textContent = 'Les étapes documentées seront affichées ici dès leur disponibilité.';
        composer.placeholder = 'Posez votre question au guide…';
        toggle.hidden = true;
        return;
    }
    const citations = get('citations');
    function showSources(example) {
        citations.replaceChildren();
        example.sources.forEach((url, i) => {
            const link = document.createElement('a');
            link.href = url; link.target = '_blank'; link.rel = 'noopener noreferrer';
            link.textContent = 'Source ' + (i + 1) + ' : ' + new URL(url).hostname;
            citations.appendChild(link);
        });
        show(citations, true);
    }
    let paused = false, visible = !('IntersectionObserver' in window), elapsed = 0;
    let phase = 'typing', index = 0, position = 0, words = [];
    const placeholder = 'Posez votre question administrative ici\u2026';
    function show(node, value) { node.hidden = !value; node.style.display = value ? '' : 'none'; }
    function reset() {
        phase = 'typing'; position = 0; elapsed = 0;
        show(user, false); show(assistant, false); show(thinking, false); show(next, false); show(citations, false);
        question.textContent = ''; answer.textContent = ''; composer.placeholder = '';
        resource.href = examples[index].href;
        resource.textContent = examples[index].link;
        container.scrollTop = 0;
        status.textContent = 'Le citoyen r\u00e9dige sa question\u2026';
    }
    function staticPreview() {
        show(user, true); show(assistant, true); show(thinking, false);
        question.textContent = examples[0].question; answer.textContent = examples[0].answer;
        composer.placeholder = placeholder; status.textContent = 'Exemple de r\u00e9ponse';
        toggle.hidden = true; show(next, true); showSources(examples[0]);
    }
    toggle.addEventListener('click', () => {
        paused = !paused;
        toggle.textContent = paused ? 'Reprendre' : 'Pause';
        toggle.setAttribute('aria-pressed', String(paused));
    });
    toggle.setAttribute('aria-pressed', 'false');
    composer.addEventListener('focus', () => { paused = true; toggle.textContent = 'Reprendre'; toggle.setAttribute('aria-pressed', 'true'); composer.placeholder = placeholder; });
    if ('IntersectionObserver' in window) {
        const observer = new IntersectionObserver(entries => { visible = entries[0].isIntersecting; });
        observer.observe(container);
    }
    reducedMotion.addEventListener('change', () => {
        if (reducedMotion.matches) staticPreview();
        else { toggle.hidden = false; reset(); }
    });
    reset();
    if (reducedMotion.matches) staticPreview();
    const timer = window.setInterval(() => {
        if (paused || !visible || document.hidden || reducedMotion.matches) return;
        elapsed += 50;
        const example = examples[index];
        if (phase === 'typing' && elapsed >= 50) {
            elapsed = 0; composer.placeholder = example.question.slice(0, ++position);
            if (position >= example.question.length) { phase = 'send'; elapsed = 0; }
        } else if (phase === 'send' && elapsed >= 650) {
            question.textContent = example.question; show(user, true);
            composer.placeholder = placeholder; show(assistant, true); show(thinking, true);
            status.textContent = 'L\u2019assistant pr\u00e9pare une r\u00e9ponse\u2026';
            phase = 'thinking'; elapsed = 0;
        } else if (phase === 'thinking' && elapsed >= 1700) {
            show(thinking, false); words = example.answer.match(/\S+\s*/g) || [];
            position = 0; phase = 'answer'; elapsed = 0;
            status.textContent = 'R\u00e9ponse en cours\u2026';
        } else if (phase === 'answer' && elapsed >= 100) {
            elapsed = 0; answer.textContent += words[position++];
            container.scrollTop = container.scrollHeight;
            if (position >= words.length) {
                phase = 'hold'; elapsed = 0; show(next, true); showSources(example);
                container.scrollTop = container.scrollHeight;

                status.textContent = 'D\u00e9monstration \u00b7 poursuivez avec votre propre question.';
            }
        } else if (phase === 'hold' && elapsed >= 10000) {
            index = (index + 1) % examples.length; reset();
        }
    }, 50);
    window.addEventListener('pagehide', event => { if (!event.persisted) clearInterval(timer); });
})();
