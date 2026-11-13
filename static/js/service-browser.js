(() => {
    'use strict';
    const node = document.getElementById('official-browser');
    if (!node) return;
    const service = JSON.parse(document.getElementById('service-workspace-data').textContent);
    const fields = document.getElementById('official-browser-fields');
    const buttons = document.getElementById('official-browser-buttons');
    const status = document.getElementById('official-browser-status');
    const image = document.getElementById('official-browser-image');
    const csrf = () => document.querySelector('[name=csrfmiddlewaretoken]')?.value || '';
    let busy = false, snapshot = null;
    let suggestions = {};
    const make = (tag, text, className) => {
        const el = document.createElement(tag);
        if (text) el.textContent = text;
        if (className) el.className = className;
        return el;
    };
    function values() {
        return Object.fromEntries([...fields.elements].filter(el => el.dataset.dirty === 'true').map(el => [
            el.name, ['checkbox', 'radio'].includes(el.type) ? String(el.checked) : el.value,
        ]));
    }
    async function command(action, payload = {}, upload = null) {
        if (busy) return;
        busy = true; node.hidden = false;
        status.replaceChildren(make('span', '', 'svc-spinner'), document.createTextNode('Le portail traite votre action…'));
        node.querySelectorAll('button,input,select,textarea').forEach(el => { el.disabled = true; });
        try {
            let body;
            const headers = {'X-CSRFToken': csrf()};
            const data = {action, action_id: crypto.randomUUID(), ...payload};
            if (upload) {
                body = new FormData();
                Object.entries(data).forEach(([key, value]) => body.append(key, typeof value === 'object' ? JSON.stringify(value) : value));
                body.append('file', upload);
            } else {
                headers['Content-Type'] = 'application/json'; body = JSON.stringify(data);
            }
            const response = await fetch('/api/rag/services/' + service.code + '/browser/', {method: 'POST', headers, body});
            const dataReceived = await response.json();
            if (!response.ok) throw new Error(dataReceived.error || 'Session indisponible.');
            snapshot = dataReceived;
            if (!snapshot.active) {
                node.hidden = true; image.removeAttribute('src'); fields.replaceChildren(); buttons.replaceChildren();
                return;
            }
            render(snapshot);
            status.textContent = snapshot.notice || 'Page du service à jour. Consultez sa réponse après chaque étape.';
        } catch (error) {
            status.textContent = error.message;
        } finally {
            busy = false;
            node.querySelectorAll('button,input,select,textarea').forEach(el => { el.disabled = false; });
        }
    }
    function render(data) {
        document.getElementById('official-browser-url').textContent = data.title + ' · ' + new URL(data.url).hostname;
        image.src = data.image;
        suggestions = {};
        document.getElementById('official-browser-suggestions').hidden = true;
        document.getElementById('official-browser-apply').hidden = true;
        fields.replaceChildren(); buttons.replaceChildren();
        (data.fields || []).forEach(field => {
            const wrapper = make('div', '', 'svc-field');
            const id = 'portal-field-' + field.ref;
            const label = make('label', field.label + (field.required ? ' *' : ''), 'svc-label'); label.htmlFor = id;
            const control = make(field.type === 'select' ? 'select' : field.type === 'textarea' ? 'textarea' : 'input', '', 'svc-input');
            control.id = id; control.name = field.ref; control.dataset.sourceName = field.name || '';
            control.dataset.label = field.label || ''; control.autocomplete = 'off';
            if (control.tagName === 'INPUT') control.type = field.type;
            if (field.required) control.setAttribute('aria-required', 'true');
            if (field.type === 'select') (field.options || []).forEach(option => {
                const item = make('option', option.label); item.value = option.value; control.append(item);
            });
            if (['checkbox', 'radio'].includes(field.type)) { control.checked = field.checked; control.className = ''; }
            else if (!['password', 'file'].includes(field.type)) control.value = field.value || '';
            if (field.type === 'file') {
                control.addEventListener('change', () => {
                    const file = control.files[0];
                    if (!file) return;
                    if (file.size > 10 * 1024 * 1024) { status.textContent = 'Pièce trop volumineuse : 10 Mo maximum.'; return; }
                    command('upload', {field: field.ref, values: values()}, file);
                });
            } else control.addEventListener('input', () => { control.dataset.dirty = 'true'; });
            wrapper.append(label, control); fields.append(wrapper);
        });
        (data.buttons || []).forEach(button => {
            const control = make('button', button.label, 'svc-btn'); control.type = 'button';
            control.addEventListener('click', () => command('button', {button: button.ref, values: values()}));
            buttons.append(control);
        });
        document.getElementById('official-browser-fill').hidden = !data.fields?.length;
        document.getElementById('official-browser-draft').hidden = !data.fields?.length;
        if (!data.fields?.length) {
            fields.append(make('p', 'Utilisez la page du service ci-dessous pour choisir votre démarche ou accéder au formulaire.', 'svc-helper'));
            node.querySelector('details').open = true;
        }
    }
    fields.addEventListener('submit', event => event.preventDefault());
    document.querySelectorAll('[data-open-official-session]').forEach(button => button.addEventListener('click', () => {
        node.hidden = false; node.scrollIntoView({behavior: 'smooth', block: 'start'});
        command('start', {url: button.dataset.openOfficialSession});
    }));
    document.getElementById('official-browser-fill').addEventListener('click', () => command('fill', {values: values()}));
    document.getElementById('official-browser-close').addEventListener('click', () => command('close'));
    node.querySelectorAll('[data-browser-action]').forEach(button => button.addEventListener('click', () => command(button.dataset.browserAction)));
    node.querySelectorAll('[data-browser-scroll]').forEach(button => button.addEventListener('click', () => command('scroll', {direction: button.dataset.browserScroll})));
    image.addEventListener('click', event => {
        if (!snapshot?.active) return;
        const rect = image.getBoundingClientRect();
        command('click', {x: Math.min(999, (event.clientX - rect.left) / rect.width * 1000), y: Math.min(719, (event.clientY - rect.top) / rect.height * 720)});
    });
    document.getElementById('official-browser-type').addEventListener('click', () => {
        const input = document.getElementById('official-browser-text');
        const value = input.value; input.value = ''; command('type', {value});
    });
    document.getElementById('official-browser-draft').addEventListener('click', () => {
        let count = 0;
        const draftFields = [...document.getElementById('official-form-draft').elements];
        for (const control of fields.elements) {
            if (['password', 'file', 'checkbox', 'radio'].includes(control.type)) continue;
            const source = draftFields.find(el => el.name === control.dataset.sourceName && el.value);
            if (source) { control.value = source.value; control.dataset.dirty = 'true'; count++; }
        }
        status.textContent = count ? count + ' champ(s) repris. Relisez les valeurs avant de les reporter au portail.' : 'Aucun champ identique renseigné dans le brouillon. Complétez les champs du service ici.';
    });
    document.getElementById('official-browser-assist').addEventListener('click', async () => {
        if (busy) return;
        busy = true;
        const preview = document.getElementById('official-browser-suggestions');
        const apply = document.getElementById('official-browser-apply');
        preview.hidden = true; apply.hidden = true;
        status.replaceChildren(make('span', '', 'svc-spinner'), document.createTextNode('Le modèle prépare des propositions à partir de votre brouillon…'));
        try {
            const values = Object.fromEntries(new FormData(document.getElementById('service-draft-form')).entries());
            const response = await fetch('/api/rag/services/' + service.code + '/prepare/', {
                method: 'POST', headers: {'Content-Type': 'application/json', 'X-CSRFToken': csrf()},
                body: JSON.stringify({use_live_form: true, values}),
            });
            const result = await response.json();
            if (!response.ok) throw new Error(result.error);
            suggestions = result.suggestions || {};
            const lines = (snapshot.fields || []).filter(field => suggestions[field.ref]).map(field => field.label + ' : ' + suggestions[field.ref]);
            preview.textContent = lines.join('\n'); preview.hidden = !lines.length; apply.hidden = !lines.length;
            status.textContent = lines.length ? 'Relisez ces propositions, puis reprenez-les dans les champs pour les ajuster avant envoi au service.' : 'Complétez le brouillon avec vos informations pour obtenir des propositions.';
        } catch (error) { status.textContent = error.message; }
        finally { busy = false; }
    });
    document.getElementById('official-browser-apply').addEventListener('click', () => {
        if (busy) return;
        for (const [ref, value] of Object.entries(suggestions)) {
            const control = fields.elements.namedItem(ref);
            if (control && !['password', 'file', 'checkbox', 'radio'].includes(control.type)) {
                control.value = value; control.dataset.dirty = 'true';
            }
        }
        status.textContent = 'Propositions reprises dans les champs. Relisez avant de continuer sur le formulaire.';
    });
})();
