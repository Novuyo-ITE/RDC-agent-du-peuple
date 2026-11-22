(() => {
    const root = document.documentElement;
    const systemTheme = matchMedia('(prefers-color-scheme: dark)');
    const languages = { fr: 'Français', ln: 'Lingála', sw: 'Kiswahili', en: 'English' };
    const getTheme = () => localStorage.getItem('theme') || 'light';
    const getVolume = () => Number(localStorage.getItem('civia-volume') ?? 100);
    const getLanguage = () => {
        const saved = localStorage.getItem('preferred_language');
        return Object.hasOwn(languages, saved) ? saved : 'fr';
    };

    function applyTheme() {
        const choice = getTheme();
        const dark = choice === 'dark' || (choice === 'auto' && systemTheme.matches);
        root.dataset.theme = dark ? 'dark' : 'light';
        root.classList.toggle('dark', dark);
        const sidebar = document.getElementById('main-sidebar');
        if (sidebar) {
            sidebar.classList.toggle('dark', choice === 'hybrid');
            if (choice === 'hybrid') sidebar.dataset.theme = 'dark';
            else delete sidebar.dataset.theme;
        }
        document.querySelectorAll('[name="civia-theme"]').forEach(input => {
            input.checked = input.value === choice;
        });
    }

    function applyLanguage() {
        const code = getLanguage();
        document.querySelectorAll('[data-civia-lang]').forEach(input => {
            input.checked = input.value === code;
        });
        document.querySelectorAll('[data-civia-language]').forEach(label => {
            label.textContent = code.toUpperCase();
            label.parentElement.setAttribute('aria-label', 'Choisir la langue — ' + languages[code]);
        });
    }

    applyTheme();
    systemTheme.addEventListener('change', applyTheme);

    document.addEventListener('DOMContentLoaded', () => {
        applyTheme();
        applyLanguage();
        document.getElementById('civia-volume').value = getVolume();
        if (location.hash === '#mic-btn') document.getElementById('mic-btn')?.focus();
    });

    document.addEventListener('input', event => {
        if (event.target.id === 'civia-volume') localStorage.setItem('civia-volume', event.target.value);
    });

    document.addEventListener('change', event => {
        const input = event.target;
        if (input.name === 'civia-theme') {
            localStorage.setItem('theme', input.value);
            applyTheme();
        }
        if (input.hasAttribute('data-civia-lang')) {
            const code = input.value;
            localStorage.setItem('preferred_language', code);
            applyLanguage();
            window.dispatchEvent(new CustomEvent('languageChanged', { detail: { code, label: languages[code] } }));
        }
    });

    document.addEventListener('click', event => {
        const focusLink = event.target.closest('[data-civia-focus]');
        const focusTarget = focusLink && document.getElementById(focusLink.dataset.civiaFocus);
        if (focusTarget) {
            [...document.querySelectorAll('.civia-dialog[open]')].reverse().forEach(dialog => dialog.close());
            requestAnimationFrame(() => focusTarget.focus());
            return;
        }
        const button = event.target.closest('[data-civia-open], [data-civia-close]');
        if (!button) return;
        if (button.hasAttribute('data-civia-close')) {
            button.closest('dialog').close();
            return;
        }
        const dialog = document.getElementById(button.dataset.civiaOpen);
        if (!dialog || dialog.open) return;
        // Keep the parent dialog open so closing this dialog returns focus to its trigger.
        dialog.showModal();
    });

    if (!('speechSynthesis' in window)) return;
    let readingButton;
    let utterance;

    function stopReading() {
        if (!readingButton) return;
        readingButton.textContent = 'Écouter la réponse';
        readingButton.setAttribute('aria-pressed', 'false');
        readingButton = undefined;
        utterance = undefined;
        speechSynthesis.cancel();
    }

    document.addEventListener('click', event => {
        const button = event.target.closest('[data-civia-read]');
        if (!button) return;
        const wasReading = readingButton === button;
        stopReading();
        if (wasReading) return;
        const response = button.closest('.civia-assistant-message').querySelector('.chat-answer-text');
        const text = response.innerText.trim();
        if (!text) return;
        const speech = new SpeechSynthesisUtterance(text);
        speech.lang = button.dataset.language || getLanguage();
        speech.volume = getVolume() / 100;
        speech.onend = speech.onerror = () => {
            if (utterance === speech) stopReading();
        };
        readingButton = button;
        utterance = speech;
        button.textContent = 'Arrêter la lecture';
        button.setAttribute('aria-pressed', 'true');
        speechSynthesis.speak(speech);
    });
    window.addEventListener('pagehide', stopReading);
})();
