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
    const examples = [
        {
            question: 'Comment pr\u00e9parer ma demande de passeport en RDC ?',
            answer: 'Je vous accompagne dans votre d\u00e9marche.\n\nCommencez par consulter la fiche du passeport pour retrouver les pi\u00e8ces demand\u00e9es, le service comp\u00e9tent et les modalit\u00e9s de d\u00e9p\u00f4t.\n\nV\u00e9rifiez les consignes en vigueur sur le portail officiel avant tout paiement. Dans quelle ville souhaitez-vous d\u00e9poser votre dossier ?'
        },
        {
            question: 'Je veux cr\u00e9er une entreprise \u00e0 Kinshasa. Par o\u00f9 commencer ?',
            answer: 'Commen\u00e7ons par votre projet.\n\nLa fiche de cr\u00e9ation d\u2019entreprise vous oriente vers le Guichet Unique et les documents \u00e0 pr\u00e9parer. Les formalit\u00e9s d\u00e9pendent notamment de la forme juridique choisie.\n\nSouhaitez-vous exercer seul ou avec des associ\u00e9s ? Je pourrai vous aider \u00e0 identifier les points \u00e0 v\u00e9rifier.'
        }
    ];
    let paused = false, visible = !('IntersectionObserver' in window), elapsed = 0;
    let phase = 'typing', index = 0, position = 0, words = [];
    const placeholder = 'Posez votre question administrative ici\u2026';
    function show(node, value) { node.hidden = !value; node.style.display = value ? '' : 'none'; }
    function reset() {
        phase = 'typing'; position = 0; elapsed = 0;
        show(user, false); show(assistant, false); show(thinking, false); show(next, false);
        question.textContent = ''; answer.textContent = ''; composer.textContent = '';
        status.textContent = 'Le citoyen r\u00e9dige sa question\u2026';
    }
    function staticPreview() {
        show(user, true); show(assistant, true); show(thinking, false);
        question.textContent = examples[0].question; answer.textContent = examples[0].answer;
        composer.textContent = placeholder; status.textContent = 'Exemple de r\u00e9ponse';
        toggle.hidden = true; show(next, true);
    }
    toggle.addEventListener('click', () => {
        paused = !paused;
        toggle.textContent = paused ? 'Reprendre' : 'Mettre en pause';
        toggle.setAttribute('aria-pressed', String(paused));
    });
    toggle.setAttribute('aria-pressed', 'false');
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
            elapsed = 0; composer.textContent = example.question.slice(0, ++position);
            if (position >= example.question.length) { phase = 'send'; elapsed = 0; }
        } else if (phase === 'send' && elapsed >= 650) {
            question.textContent = example.question; show(user, true);
            composer.textContent = placeholder; show(assistant, true); show(thinking, true);
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
                phase = 'hold'; elapsed = 0; show(next, true);
                resource.textContent = index === 0 ? 'Consulter les d\u00e9marches du passeport \u2192' : 'Explorer la cr\u00e9ation d\u2019entreprise \u2192';
                status.textContent = 'D\u00e9monstration \u00b7 poursuivez avec votre propre question.';
            }
        } else if (phase === 'hold' && elapsed >= 6500) {
            index = (index + 1) % examples.length; reset();
        }
    }, 50);
    window.addEventListener('pagehide', event => { if (!event.persisted) clearInterval(timer); });
})();
