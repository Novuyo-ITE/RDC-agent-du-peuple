(() => {
    const dialog = document.getElementById('chat-delete-dialog');
    const cancel = document.getElementById('chat-delete-cancel');
    const confirm = document.getElementById('chat-delete-confirm');
    const error = document.getElementById('chat-delete-error');
    let sessionId = null;
    let trigger = null;
    let busy = false;

    window.openChatDeleteDialog = (id, source) => {
        if (dialog.open || !/^[A-Za-z0-9_-]{1,120}$/.test(id)) return;
        sessionId = id;
        trigger = source;
        document.getElementById('chat-delete-name').textContent =
            document.getElementById('title-' + id)?.textContent.trim() || 'Consultation';
        error.hidden = true;
        dialog.showModal();
        cancel.focus();
    };

    cancel.addEventListener('click', () => { if (!busy) dialog.close(); });
    dialog.addEventListener('cancel', event => { if (busy) event.preventDefault(); });
    dialog.addEventListener('keydown', event => {
        if (event.key !== 'Tab') return;
        if (busy) { event.preventDefault(); return; }
        if (event.shiftKey && document.activeElement === cancel) {
            event.preventDefault();
            confirm.focus();
        } else if (!event.shiftKey && document.activeElement === confirm) {
            event.preventDefault();
            cancel.focus();
        }
    });
    // Only a click beginning and ending on the backdrop dismisses the popup.
    let backdropPress = false;
    dialog.addEventListener('pointerdown', event => { backdropPress = event.target === dialog; });
    dialog.addEventListener('click', event => {
        if (!busy && backdropPress && event.target === dialog) dialog.close();
        backdropPress = false;
    });
    dialog.addEventListener('close', () => {
        sessionId = null;
        if (trigger?.isConnected) trigger.focus();
        else document.querySelector('#recent-consultations-list button')?.focus();
        trigger = null;
    });

    confirm.addEventListener('click', async () => {
        if (busy || !sessionId) return;
        const id = sessionId;
        busy = true;
        cancel.disabled = confirm.disabled = true;
        confirm.textContent = 'Suppression…';
        dialog.setAttribute('aria-busy', 'true');
        error.hidden = true;
        try {
            const response = await fetch(`/api/rag/sessions/${id}/delete/`, {
                method: 'DELETE', headers: { 'X-CSRFToken': getCookie('csrftoken') }
            });
            if (!response.ok) throw new Error('HTTP ' + response.status);
            document.getElementById('sess-item-' + id)?.remove();
            window.dispatchEvent(new CustomEvent('chat-session-deleted', { detail: { id } }));
            if (window.currentSessionId === id && typeof startNewChat === 'function') startNewChat();
            const remaining = document.querySelectorAll('[id^="sess-item-"]').length;
            const count = document.getElementById('sessions-count');
            if (count) count.textContent = remaining || '';
            if (!remaining) loadChromaSessions();
            dialog.close();
        } catch (err) {
            error.textContent = 'Impossible de supprimer cette conversation. Veuillez réessayer.';
            error.hidden = false;
        } finally {
            busy = false;
            cancel.disabled = confirm.disabled = false;
            confirm.textContent = 'Supprimer';
            dialog.removeAttribute('aria-busy');
        }
    });
})();
