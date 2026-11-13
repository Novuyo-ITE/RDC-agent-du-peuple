(() => {
    const examples = [
        'Besoin d’un passeport biométrique ?',
        'Comprendre la guerre à l’Est ?',
        'Obtenir un acte de naissance ?',
        'Créer une entreprise en RDC ?',
        'Suivre l’actualité congolaise ?',
    ];
    const colors = ['blue', 'red', 'yellow'];
    const container = document.getElementById('chat-messages');
    if (!container) return;
    const motion = window.matchMedia('(prefers-reduced-motion: reduce)');
    let target = null, timer = null, index = 0, colorIndex = 0, length = 0, deleting = true;

    function schedule(delay) { timer = window.setTimeout(tick, delay); }
    function tick() {
        if (!target || !target.isConnected || motion.matches) return;
        if (document.hidden) { schedule(1000); return; }
        const text = examples[index];
        length += deleting ? -1 : 1;
        target.textContent = text.slice(0, length);
        if (deleting && length === 0) {
            index = (index + 1) % examples.length;
            colorIndex = (colorIndex + 1) % colors.length;
            target.dataset.color = colors[colorIndex];
            deleting = false;
            schedule(350);
        } else if (!deleting && length === text.length) {
            deleting = true;
            schedule(2600);
        } else {
            schedule(deleting ? 35 : 65);
        }
    }
    function restart() {
        window.clearTimeout(timer);
        target = container.querySelector('#welcome-card [data-chat-hero-example]');
        if (!target) return;
        index = 0;
        colorIndex = 0;
        length = examples[0].length;
        deleting = true;
        target.textContent = examples[0];
        target.dataset.color = colors[colorIndex];
        if (!motion.matches) schedule(2600);
    }
    new MutationObserver(() => {
        const next = container.querySelector('#welcome-card [data-chat-hero-example]');
        if (next !== target) restart();
    }).observe(container, {childList:true});
    if (motion.addEventListener) motion.addEventListener('change', restart);
    restart();
})();
