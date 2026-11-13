(() => {
    'use strict';
    const csrf = () => document.querySelector('[name=csrfmiddlewaretoken]')?.value || '';
    const element = (tag, className, text) => {
        const el = document.createElement(tag);
        if (className) el.className = className;
        if (text) el.textContent = text;
        return el;
    };
    const headline = document.getElementById('service-headline-cycle');
    if (headline) {
        const phrases = [
            {text: 'Comprenez vos d\u00e9marches en RDC...', className: 'svc-headline-need'},
            {text: 'Besoin d\u2019un passeport...', className: 'svc-headline-ai'},
            {text: 'Besoin d\u2019un permis de conduire...', className: 'svc-headline-need'},
            {text: 'Besoin d\u2019un acte de naissance...', className: 'svc-headline-ai'},
            {text: 'Envie de cr\u00e9er une entreprise...', className: 'svc-headline-need'},
            {text: 'Une IA inclusive vous guide pas \u00e0 pas...', className: 'svc-headline-ai'},
        ];
        const motion = window.matchMedia('(prefers-reduced-motion: reduce)');
        let timer;
        const startHeadline = () => {
            clearTimeout(timer);
            if (motion.matches) {
                headline.textContent = phrases[0].text;
                headline.className = 'svc-headline-need';
                return;
            }
            let index = 0, length = 0, deleting = false;
            headline.textContent = '';
            const tick = () => {
                const phrase = phrases[index];
                headline.className = phrase.className;
                length += deleting ? -1 : 1;
                const visibleText = phrase.text.slice(0, length);
                headline.textContent = visibleText;
                if (visibleText.endsWith('.')) {
                    headline.textContent = visibleText.slice(0, -1);
                    headline.append(element('span', 'svc-headline-dot', '.'));
                }
                let delay = deleting ? 65 : 115;
                if (!deleting && length === phrase.text.length) {
                    deleting = true;
                    delay = 2400;
                } else if (deleting && length === 0) {
                    deleting = false;
                    index = (index + 1) % phrases.length;
                    delay = 350;
                }
                timer = setTimeout(tick, delay);
            };
            tick();
        };
        motion.addEventListener('change', startHeadline);
        startHeadline();
    }
    const discovery = document.getElementById('service-discovery-form');
    if (discovery) {
        let busy = false;
        document.querySelectorAll('[data-need]').forEach(button => button.addEventListener('click', () => {
            document.getElementById('service-need').value = button.dataset.need;
            discovery.requestSubmit();
        }));
        discovery.addEventListener('submit', async event => {
            event.preventDefault();
            const query = document.getElementById('service-need').value.trim();
            if (!query || busy) return;
            busy = true;
            const button = document.getElementById('service-discover-btn');
            const spinner = document.getElementById('service-discovery-spinner');
            const status = document.getElementById('service-discovery-status');
            const results = document.getElementById('service-recommendations');
            button.disabled = true; spinner.hidden = false;
            status.textContent = 'Votre guide recherche les démarches adaptées…';
            results.replaceChildren();
            try {
                const response = await fetch('/api/rag/services/discover/', {
                    method: 'POST', headers: {'Content-Type': 'application/json', 'X-CSRFToken': csrf()},
                    body: JSON.stringify({query}),
                });
                const data = await response.json();
                if (!response.ok) throw new Error(data.error || 'Recherche indisponible.');
                for (const service of data.recommendations || []) {
                    const card = element('a', 'svc-result');
                    card.href = service.url;
                    card.append(element('strong', '', service.name), element('p', '', service.reason), element('span', '', 'Préparer cette démarche →'));
                    results.append(card);
                }
                status.textContent = data.message || (data.recommendations.length ? 'Voici des services à explorer. Vérifiez les conditions dans chaque fiche.' : 'Aucune correspondance. Précisez votre besoin ou parcourez les catégories ci-dessous.');
            } catch (error) { status.textContent = 'Recherche IA indisponible. Vous pouvez utiliser le catalogue ci-dessous.'; }
            finally { busy = false; button.disabled = false; spinner.hidden = true; }
        });
    }

    const dataNode = document.getElementById('service-workspace-data');
    if (!dataNode) return;
    const service = JSON.parse(dataNode.textContent);
    const key = 'service-draft:' + service.code;
    const historyKey = 'service-guide-history:' + service.code;
    const sessionKey = 'service-guide-session:' + service.code;
    let guideSessionId = new URLSearchParams(location.search).get('session');
    try { guideSessionId = guideSessionId || sessionStorage.getItem(sessionKey); } catch(error) { /* Use URL state. */ }
    const resumeSession = Boolean(guideSessionId);
    guideSessionId = guideSessionId || 'service_' + crypto.randomUUID().replaceAll('-', '');
    window.currentSessionId = guideSessionId;
    window.currentChatContext = {kind: 'service', id: service.code};
    const draft = document.getElementById('service-draft-form');
    const officialDraft = document.getElementById('official-form-draft');
    let officialFields = [], savedOfficialValues = {}, suggestedValues = {}, savedReadyDocuments = [];
    let checks = [...document.querySelectorAll('[data-document-index]')];
    const status = document.getElementById('service-guide-status');
    const log = document.getElementById('service-guide-messages');
    const send = document.getElementById('service-guide-send');
    const guideForm = document.getElementById('service-guide-form');
    let stage = 'understand', focusedField = '', history = [], busy = false, guideRequest = null;
    send.addEventListener('click', event => {
        if (guideRequest) { event.preventDefault(); guideRequest.abort(); }
    });
    const fields = () => Object.fromEntries(new FormData(draft).entries());
    const checked = () => checks.filter(input => input.checked).map(input => Number(input.dataset.documentIndex));

    function summary() {
        const values = fields();
        const ready = checked();
        return [
            'DOSSIER DE PRÉPARATION — NON DÉPOSÉ', service.name, service.institution,
            'Source officielle : ' + (service.portal || 'Non renseignée'),
            'Consultée le : ' + (service.source_checked_at || 'Non confirmée'), '',
            'Demandeur : ' + (values.applicant || 'Non renseigné'),
            'Ville envisagée : ' + (values.city || 'Non renseignée'),
            'Objet : ' + (values.purpose || 'Non renseigné'),
            'Points à confirmer : ' + (values.notes || 'Aucun renseigné'), '',
            ...officialFields.map(field => field.label + ' : ' + (officialDraft.elements.namedItem(field.name)?.value || 'Non renseigné')),
            'Pièces déclarées prêtes : ' + ready.length + '/' + service.documents.length,
            ...service.documents.map((doc, index) => (ready.includes(index) ? '[Prête] ' : '[À préparer] ') + doc), '',
            'Frais publiés : ' + (service.live_facts?.fees?.text || 'Non confirmés par la source consultée'),
            'Délai publié : ' + (service.live_facts?.processing_time?.text || 'Non confirmé par la source consultée'),
            'Instructions de paiement : ' + (service.live_facts?.payment?.text || 'Non confirmées par la source consultée'),
            'Portail : ' + (service.portal || 'Non renseigné'),
            ...service.locations.map(location => location.city + ' : ' + location.address), '',
            'Brouillon personnel. Ne remplace pas le formulaire officiel. Aucune demande soumise.',
        ].join('\n');
    }
    function updateProgress() {
        const count = checked().length;
        const percent = checks.length ? Math.round(count / checks.length * 100) : 0;
        document.getElementById('documents-ready').textContent = count + ' pièce(s) déclarée(s) prête(s)';
        document.getElementById('documents-progress').setAttribute('aria-valuenow', percent);
        document.getElementById('documents-progress-fill').style.width = percent + '%';
        document.getElementById('service-review').textContent = summary();
    }
    function saveDraft() {
        updateProgress();
        try {
            sessionStorage.setItem(key, JSON.stringify({values: fields(), checked: checked(), readyDocuments: checked().map(index => service.documents[index]), officialValues: Object.fromEntries(new FormData(officialDraft).entries())}));
            document.getElementById('draft-save-status').textContent = 'Brouillon enregistré dans cet onglet. Les champs ne sont pas envoyés automatiquement au guide IA.';
        } catch (error) {
            document.getElementById('draft-save-status').textContent = 'Enregistrement local indisponible. Téléchargez votre récapitulatif avant de quitter.';
        }
    }
    try {
        const saved = JSON.parse(sessionStorage.getItem(key) || 'null');
        if (saved && saved.values && Array.isArray(saved.checked)) {
            savedOfficialValues = saved.officialValues || {};
            savedReadyDocuments = Array.isArray(saved.readyDocuments) ? saved.readyDocuments : [];
            for (const input of draft.elements) if (input.name && typeof saved.values[input.name] === 'string') input.value = saved.values[input.name];
        }
    } catch (error) { /* Start with an empty draft if browser storage is unavailable. */ }
    updateProgress();
    draft.addEventListener('input', saveDraft);
    officialDraft.addEventListener('input', saveDraft);
    officialDraft.addEventListener('submit', event => event.preventDefault());
    officialDraft.addEventListener('focusin', event => { if (event.target.dataset.fieldLabel) focusedField = event.target.dataset.fieldLabel; });
    checks.forEach(input => input.addEventListener('change', saveDraft));
    document.getElementById('clear-service-draft').addEventListener('click', () => {
        draft.reset(); officialDraft.reset(); savedOfficialValues = {}; savedReadyDocuments = []; checks.forEach(input => { input.checked = false; });
        try { sessionStorage.removeItem(key); } catch (error) { /* Nothing to remove. */ }
        updateProgress(); document.getElementById('draft-save-status').textContent = 'Brouillon effacé.';
    });

    function setStage(next, focus = false) {
        stage = next;
        document.querySelectorAll('[data-stage]').forEach(tab => {
            const active = tab.dataset.stage === next;
            tab.setAttribute('aria-selected', active);
            tab.tabIndex = active ? 0 : -1;
            document.getElementById('step-' + tab.dataset.stage).hidden = !active;
            if (active && focus) tab.focus();
        });
        updateProgress();
    }
    document.querySelectorAll('[data-stage]').forEach(tab => {
        tab.addEventListener('click', () => setStage(tab.dataset.stage));
        tab.addEventListener('keydown', event => {
            const stages = ['understand', 'prepare', 'apply'];
            const index = stages.indexOf(stage);
            if (['ArrowRight', 'ArrowLeft', 'Home', 'End'].includes(event.key)) {
                event.preventDefault();
                const next = event.key === 'Home' ? 0 : event.key === 'End' ? 2 : (index + (event.key === 'ArrowRight' ? 1 : 2)) % 3;
                setStage(stages[next], true);
            }
        });
    });
    document.querySelectorAll('[data-go-stage]').forEach(button => button.addEventListener('click', () => setStage(button.dataset.goStage, true)));
    draft.addEventListener('focusin', event => { if (event.target.dataset.fieldLabel) focusedField = event.target.dataset.fieldLabel; });
    document.getElementById('download-service-draft').addEventListener('click', () => {
        const url = URL.createObjectURL(new Blob([summary()], {type: 'text/plain;charset=utf-8'}));
        const link = element('a'); link.href = url; link.download = service.code + '-preparation.txt';
        document.body.append(link); link.click(); link.remove(); setTimeout(() => URL.revokeObjectURL(url), 1000);
    });
    document.getElementById('print-service-draft').addEventListener('click', () => { updateProgress(); window.print(); });

    function appendMessage(role, text, sources = []) {
        const message = element('div', 'svc-message ' + role);
        const content = element('div', '', text);
        message.append(content); message._chatCopyContent = content;
        if (role === 'assistant') ChatMarkdown.render(content, text);
        if (role === 'assistant' && sources.length && window.SourceBriefs) message.append(SourceBriefs.create(sources));
        if (window.ChatCopy) ChatCopy.attach(message, text, role);
        log.append(message); log.scrollTop = log.scrollHeight;
        return message;
    }
    try {
        const saved = JSON.parse(sessionStorage.getItem(historyKey) || '[]');
        if (Array.isArray(saved)) {
            history = saved.filter(turn => turn && ['user', 'assistant'].includes(turn.role) && typeof turn.content === 'string').slice(-100);
            history.forEach(turn => appendMessage(turn.role, turn.content, turn.sources));
        }
    } catch (error) { /* The guide remains usable without browser storage. */ }
    if (resumeSession) {
        busy = true; CompactChat.setBusy(send, true);
        document.getElementById('service-guide-spinner').hidden = false;
        status.textContent = 'Chargement de la conversation…';
        fetch('/api/rag/sessions/' + encodeURIComponent(guideSessionId) + '/').then(async response => {
            if (!response.ok) throw new Error();
            const result = await response.json();
            if (result.session?.kind === 'service' && result.session.service_code === service.code) {
                history = (result.messages || []).filter(turn => ['user', 'assistant'].includes(turn.role) && typeof turn.content === 'string')
                    .map(turn => ({role: turn.role, content: turn.content.slice(0, 8000), sources: Array.isArray(turn.sources) ? turn.sources : []})).slice(-100);
                log.querySelectorAll('.svc-message').forEach(message => message.remove());
                history.forEach(turn => appendMessage(turn.role, turn.content, turn.sources));
                if (typeof markActiveSession === 'function') markActiveSession(guideSessionId);
            }
            status.textContent = 'Vous pouvez reprendre cette conversation.';
        }).catch(() => { status.textContent = 'Historique serveur indisponible. Les messages de cet onglet restent accessibles.'; })
        .finally(() => { busy = false; CompactChat.setBusy(send, false); document.getElementById('service-guide-spinner').hidden = true; });
    }
    window.addEventListener('chat-session-deleted', event => {
        if (event.detail.id !== guideSessionId) return;
        history = []; log.querySelectorAll('.svc-message').forEach(message => message.remove());
        guideSessionId = 'service_' + crypto.randomUUID().replaceAll('-', ''); window.currentSessionId = guideSessionId;
        try { sessionStorage.removeItem(historyKey); sessionStorage.removeItem(sessionKey); } catch(error) { /* Clear in-memory state. */ }
        const url = new URL(location.href); url.searchParams.delete('session'); window.history.replaceState(null, '', url);
    });
    async function ask(query) {
        if (busy || !query.trim()) return;
        busy = true; guideRequest = new AbortController();
        const controller = guideRequest;
        CompactChat.setBusy(send, true, true);
        document.getElementById('service-guide-spinner').hidden = false;
        log.setAttribute('aria-busy', 'true');
        status.textContent = 'Le guide prépare sa réponse…';
        appendMessage('user', query);
        let answer = '', bubble = null, complete = false, sources = [], historySaved = null;
        try {
            if (window.chatHistoryMigration) await window.chatHistoryMigration;
            const response = await fetch('/api/rag/services/' + service.code + '/guide/', {
                method: 'POST', headers: {'Content-Type': 'application/json', 'X-CSRFToken': csrf()},
                signal: controller.signal,
                body: JSON.stringify({query, session_id: guideSessionId, history: history.slice(-100), stage, field: focusedField, checked_documents: checked(),
                    language: localStorage.getItem('preferred_language') || 'fr', web_search: document.getElementById('service-guide-web').checked}),
            });
            if (!response.ok) throw new Error('Le guide est momentanément indisponible.');
            const reader = response.body.getReader(), decoder = new TextDecoder();
            let buffer = '';
            while (true) {
                const {done, value} = await reader.read();
                buffer += decoder.decode(value || new Uint8Array(), {stream: !done});
                const frames = buffer.split('\n\n'); buffer = frames.pop();
                for (const frame of frames) {
                    if (!frame.startsWith('data:')) continue;
                    const item = JSON.parse(frame.slice(5));
                    if (item.type === 'status') status.textContent = item.message;
                    if (item.type === 'sources') sources = item.sources || [];
                    if (item.type === 'token') {
                        if (!bubble) bubble = appendMessage('assistant', '');
                        answer += item.token; ChatMarkdown.render(bubble._chatCopyContent, answer); if (window.ChatCopy) ChatCopy.setText(bubble, answer);
                        status.textContent = 'Réponse en cours…'; log.scrollTop = log.scrollHeight;
                    }
                    if (item.type === 'error') throw new Error(item.message);
                    if (item.type === 'done') {
                        complete = true; historySaved = item.history_saved;
                        if (item.session_id) {
                            guideSessionId = item.session_id; window.currentSessionId = guideSessionId;
                            try { sessionStorage.setItem(sessionKey, guideSessionId); } catch(error) { /* Use URL state. */ }
                            const url = new URL(location.href); url.searchParams.set('session', guideSessionId); window.history.replaceState(null, '', url);
                        }
                    }
                }
                if (done) break;
            }
            if (!complete) throw new Error('Connexion interrompue. Réessayez votre question.');
            if (bubble && sources.length && window.SourceBriefs) bubble.append(SourceBriefs.create(sources));
            history.push({role: 'user', content: query}, {role: 'assistant', content: answer.slice(0, 8000), sources});
            history = history.slice(-100);
            try { sessionStorage.setItem(historyKey, JSON.stringify(history)); } catch (error) { /* Keep the current conversation in memory. */ }
            status.textContent = 'Vous pouvez poser une autre question.';
            if (historySaved === false) status.textContent = 'La sauvegarde dans l’historique commun a échoué ; les messages restent dans cet onglet.';
            if (typeof loadChromaSessions === 'function') loadChromaSessions();
        } catch (error) {
            status.textContent = error.name === 'AbortError' ? 'Génération arrêtée.' : error.message;
            if (error.name === 'AbortError' && answer.trim()) {
                history.push({role: 'user', content: query}, {role: 'assistant', content: answer.slice(0, 8000), sources});
                history = history.slice(-100);
                try { sessionStorage.setItem(historyKey, JSON.stringify(history)); } catch (_) {}
            }
            if (!answer) document.getElementById('service-guide-query').value = query;
        } finally {
            busy = false; guideRequest = null; CompactChat.setBusy(send, false);
            document.getElementById('service-guide-spinner').hidden = true;
            log.setAttribute('aria-busy', 'false');
        }
    }
    guideForm.addEventListener('submit', event => {
        event.preventDefault(); if (busy) return;
        const input = document.getElementById('service-guide-query');
        const query = input.value.trim(); if (!query) return;
        input.value = ''; ask(query);
    });
    document.querySelectorAll('[data-ask]').forEach(button => button.addEventListener('click', () => ask(button.dataset.ask)));
    document.querySelectorAll('[data-help-field]').forEach(button => button.addEventListener('click', () => {
        focusedField = button.dataset.helpField;
        ask('Aide-moi à remplir le champ « ' + focusedField + ' » de mon brouillon de préparation. Que dois-je y indiquer ?');
    }));

    function renderSearchSource(snapshot) {
        const target = document.getElementById('source-reader-content');
        const note = document.getElementById('source-reader-status');
        target.replaceChildren();
        const content = snapshot.source_content || {};
        if (!snapshot.available || !content.sections?.length) {
            note.textContent = content.format === 'pdf'
                ? 'Ce PDF ne contient pas de texte extractible. Consultez le document original.'
                : 'Le contenu de cette source est inaccessible pour le moment. Consultez le document original.';
            return;
        }
        note.textContent = content.format === 'pdf'
            ? 'Texte extrait du PDF (' + content.page_count + ' pages).'
            : 'Texte lu sur la page officielle.';
        if (content.truncated) note.textContent += ' Affichage partiel : consultez le document original pour la suite.';
        for (const section of content.sections) {
            const block = element('section', 'svc-source-section');
            block.append(element('h3', '', section.title), element('p', 'svc-source-text', section.text));
            const link = element('a', 'svc-guide-source', 'Voir ce passage dans la source \u2197');
            let url;
            try { url = new URL(section.url); } catch (error) { target.append(block); continue; }
            if (['https:', 'http:'].includes(url.protocol)) {
                link.href = url.href; link.target = '_blank'; link.rel = 'noopener noreferrer'; block.append(link);
            }
            target.append(block);
        }
    }

    async function loadOfficialInstructions() {
        const officialStatus = document.getElementById('official-service-status');
        try {
            let snapshot = JSON.parse(document.getElementById('service-initial-snapshot')?.textContent || '{}');
            if (!snapshot.available) {
                const response = await fetch('/api/rag/services/' + service.code + '/official/');
                if (!response.ok) throw new Error();
                snapshot = await response.json();
            }
            if (service.is_search_source) { renderSearchSource(snapshot); return; }
            const facts = snapshot.facts || {};
            service.live_facts = facts;
            service.source_checked_at = snapshot.checked_at || '';
            service.documents = (facts.documents || []).map(fact => fact.text);
            function appendSource(parent, fact) {
                try {
                    const url = new URL(fact.url);
                    if (!['http:', 'https:'].includes(url.protocol)) return;
                    const link = element('a', 'svc-guide-source', 'Source : ' + url.hostname + ' ↗');
                    link.href = url.href; link.target = '_blank'; link.rel = 'noopener noreferrer'; parent.append(link);
                } catch (error) { /* An invalid source link is never made clickable. */ }
            }
            for (const name of ['description', 'eligibility', 'fees', 'processing_time', 'office', 'payment']) {
                const target = document.getElementById('live-service-' + name);
                target.textContent = facts[name]?.text || 'Information non retrouvée sur la page officielle consultée. À confirmer auprès de l’institution.';
                if (facts[name]) appendSource(target, facts[name]);
            }
            const documentList = document.getElementById('live-service-documents');
            const checklist = document.getElementById('live-document-checklist');
            documentList.replaceChildren(); checklist.replaceChildren();
            (facts.documents || []).forEach((fact, index) => {
                const li = element('li', '', fact.text); appendSource(li, fact); documentList.append(li);
                const label = element('label', 'svc-check');
                const check = element('input'); check.type = 'checkbox'; check.dataset.documentIndex = index;
                check.checked = savedReadyDocuments.includes(fact.text);
                check.addEventListener('change', saveDraft);
                label.append(check, element('span', '', fact.text)); checklist.append(label);
            });
            checks = [...checklist.querySelectorAll('input')];
            document.getElementById('documents-total').textContent = service.documents.length + ' pièce(s) lue(s) sur la source';
            if (!service.documents.length) {
                documentList.append(element('li', 'svc-helper', 'Liste de pièces non retrouvée sur la source consultée.'));
                checklist.append(element('p', 'svc-helper', 'Aucune liste de pièces confirmée : consultez l’institution.'));
            }
            updateProgress();
            const checkedDate = snapshot.checked_at ? new Date(snapshot.checked_at).toLocaleDateString('fr-FR') : '';
            officialStatus.textContent = snapshot.available ?
                'Sources officielles consultées' + (checkedDate ? ' le ' + checkedDate : '') + '. Consultez les liens pour vérifier les conditions en vigueur.' :
                'Le portail n’a pas pu être lu. Consultez directement la source officielle.';
            if (snapshot.source_url) {
                const source = element('a', '', ' Ouvrir la source ↗');
                const url = new URL(snapshot.source_url);
                if (['http:', 'https:'].includes(url.protocol)) {
                    source.href = url.href; source.target = '_blank'; source.rel = 'noopener noreferrer';
                    source.style.color = 'var(--svc-blue)'; officialStatus.append(source);
                }
            }
            if (snapshot.steps?.length) {
                const list = document.getElementById('official-service-step-list');
                list.replaceChildren();
                snapshot.steps.forEach((text, index) => {
                    const item = element('li', '', text);
                    if (facts.steps?.[index]) appendSource(item, facts.steps[index]);
                    list.append(item);
                });
                document.getElementById('official-service-steps').hidden = false;
            } else if (snapshot.available) {
                officialStatus.append(document.createTextNode(' Aucune procédure numérotée détectée : consultez la page de demande officielle pour l’ordre exact.'));
            }
            if (!snapshot.forms?.length) return;
            officialFields = snapshot.forms[0].fields;
            officialFields.forEach((field, index) => {
                const wrapper = element('div', 'svc-field');
                const label = element('label', 'svc-label', field.label + (field.required ? ' *' : ''));
                const control = element(field.type === 'select' ? 'select' : field.type === 'textarea' ? 'textarea' : 'input', 'svc-input');
                if (control.tagName === 'INPUT') control.type = field.type;
                if (['checkbox', 'radio'].includes(field.type)) { control.className = ''; control.value = field.value || 'on'; }
                if (field.type === 'select') for (const option of field.options || []) {
                    const item = element('option', '', option.label); item.value = option.value; control.append(item);
                }
                control.name = field.name; control.id = 'official-field-' + index;
                control.required = field.required; control.dataset.fieldLabel = field.label;
                if (typeof savedOfficialValues[field.name] === 'string' && !['checkbox', 'radio'].includes(field.type)) control.value = savedOfficialValues[field.name];
                label.htmlFor = control.id;
                const help = element('button', 'svc-field-help', 'Expliquer ce champ'); help.type = 'button';
                help.addEventListener('click', () => { focusedField = field.label; ask('Explique le champ officiel « ' + field.label + ' ». Comment le remplir selon la page source ?'); });
                wrapper.append(label, control, help); officialDraft.append(wrapper);
            });
            document.getElementById('official-form-section').hidden = false;
            updateProgress();
        } catch (error) {
            if (service.is_search_source) { renderSearchSource({available: false}); return; }
            officialStatus.textContent = 'Lecture du portail indisponible. Ouvrez la source officielle pour confirmer les étapes et le formulaire.';
        }
    }
    loadOfficialInstructions();

    document.getElementById('official-form-help').addEventListener('click', async () => {
        const button = document.getElementById('official-form-help');
        const note = document.getElementById('official-form-suggestion-status');
        const preview = document.getElementById('official-form-suggestions');
        const apply = document.getElementById('official-form-apply-suggestions');
        button.disabled = true; apply.hidden = true; preview.hidden = true;
        note.replaceChildren(element('span', 'svc-spinner'), document.createTextNode('Le modèle prépare des suggestions…'));
        try {
            const response = await fetch('/api/rag/services/' + service.code + '/prepare/', {
                method: 'POST', headers: {'Content-Type': 'application/json', 'X-CSRFToken': csrf()},
                body: JSON.stringify({values: {...fields(), ...Object.fromEntries(new FormData(officialDraft).entries())}}),
            });
            const result = await response.json();
            if (!response.ok) throw new Error(result.error || 'Aide au remplissage indisponible.');
            suggestedValues = result.suggestions || {};
            const lines = officialFields.filter(field => suggestedValues[field.name]).map(field => field.label + ' : ' + suggestedValues[field.name]);
            preview.textContent = lines.join('\n'); preview.hidden = !lines.length;
            apply.hidden = !lines.length;
            note.textContent = lines.length ? 'Relisez ces valeurs avant de les appliquer. Aucun envoi au portail officiel.' : 'Informations insuffisantes pour proposer des valeurs. Complétez votre brouillon ou demandez au guide.';
        } catch (error) { note.textContent = error.message; }
        finally { button.disabled = false; }
    });
    document.getElementById('official-form-apply-suggestions').addEventListener('click', () => {
        for (const [name, value] of Object.entries(suggestedValues)) {
            const input = officialDraft.elements.namedItem(name);
            if (input && 'value' in input && !['checkbox', 'radio'].includes(input.type)) input.value = value;
        }
        saveDraft();
        document.getElementById('official-form-apply-suggestions').hidden = true;
        document.getElementById('official-form-suggestion-status').textContent = 'Suggestions appliquées au brouillon. Vérifiez chaque champ sur le site officiel avant de déposer.';
    });
})();
