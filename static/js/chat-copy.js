/* Copy a message's own text without collecting source cards or UI controls. */
(() => {
    let touchActiveMessage = null;
    document.addEventListener('pointerdown', event => {
        if (event.pointerType !== 'touch') return;
        const message = event.target.closest?.('.chat-copy-container') || null;
        if (touchActiveMessage && touchActiveMessage !== message) touchActiveMessage.classList.remove('is-copy-active');
        touchActiveMessage = message;
        if (message) message.classList.add('is-copy-active');
    });
    function fallbackCopy(text) {
        const input = document.createElement('textarea');
        const previous = document.activeElement;
        input.value = text;
        input.setAttribute('readonly', '');
        input.style.cssText = 'position:fixed;left:-9999px;top:0;opacity:0';
        document.body.append(input);
        try {
            input.select();
            if (!document.execCommand('copy')) throw new Error('Copy unavailable');
        } finally {
            input.remove();
            if (previous && previous.isConnected) previous.focus({preventScroll:true});
        }
    }
    async function copy(text) {
        if (navigator.clipboard && navigator.clipboard.writeText) {
            try { await navigator.clipboard.writeText(text); return; } catch (_) { /* Try the browser fallback. */ }
        }
        fallbackCopy(text);
    }
    function setText(container, text) {
        if (!container) return;
        container._chatCopyText = typeof text === 'string' ? text : '';
        if (container._chatCopyButton) container._chatCopyButton.hidden = !container._chatCopyText.trim();
    }
    function attach(container, text, role) {
        if (!container) return;
        if (container._chatCopyButton) { setText(container, text); return; }
        container.classList.add('chat-copy-container');
        const button = document.createElement('button');
        button.type = 'button';
        button.className = 'chat-copy-button';
        const label = role === 'assistant' ? 'Copier la réponse' : 'Copier le message';
        button.setAttribute('aria-label', label);
        button.title = label;
        button.innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="8" y="8" width="11" height="11" rx="2"></rect><path d="M16 8V6a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v8a2 2 0 0 0 2 2h2"></path></svg>';
        const status = document.createElement('span');
        status.textContent = 'Copier';
        status.setAttribute('aria-live', 'polite');
        button.append(status);
        button.addEventListener('click', async () => {
            try {
                await copy(container._chatCopyText);
                status.textContent = 'Copié !';
            } catch (_) {
                status.textContent = 'Copie impossible';
            }
            window.clearTimeout(button._chatCopyReset);
            button._chatCopyReset = window.setTimeout(() => { status.textContent = 'Copier'; }, 2000);
        });
        container._chatCopyButton = button;
        container.append(button);
        setText(container, text);
    }
    window.ChatCopy = {attach, setText};
})();
