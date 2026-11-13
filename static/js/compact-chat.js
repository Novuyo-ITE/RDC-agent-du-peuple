/* Shared voice input and send-button states for contextual assistants. */
(() => {
    function setBusy(button, busy, canStop = false) {
        button.classList.toggle('is-busy', busy);
        button.disabled = busy && !canStop;
        const send = button.querySelector('.compact-chat-send-icon');
        const stop = button.querySelector('.compact-chat-stop-icon');
        if (send) send.hidden = busy && canStop;
        if (stop) stop.hidden = !(busy && canStop);
        const label = busy && canStop ? 'Arrêter la génération' : (button.dataset.sendLabel || 'Envoyer la question');
        button.setAttribute('aria-label', label);
        button.title = label;
    }
    function setupVoice(button) {
        const input = document.getElementById(button.dataset.target);
        const status = document.getElementById(button.dataset.status);
        if (!input || !status) return;
        let recorder, chunks = [], audioContext, source, frame;
        function stopSpectrum() {
            if (frame) cancelAnimationFrame(frame);
            frame = null;
            if (source) source.disconnect();
            source = null;
            if (audioContext) audioContext.close().catch(() => {});
            audioContext = null;
        }
        function spectrum(stream) {
            const AudioContextClass = window.AudioContext || window.webkitAudioContext;
            if (!AudioContextClass) return;
            try {
                audioContext = new AudioContextClass();
                const analyser = audioContext.createAnalyser(); analyser.fftSize = 256;
                source = audioContext.createMediaStreamSource(stream); source.connect(analyser);
                const frequencies = new Uint8Array(analyser.frequencyBinCount);
                const bars = [...button.querySelectorAll('.compact-chat-mic-bars span')];
                const maxBin = Math.min(frequencies.length, Math.max(6, Math.ceil(3000 * analyser.fftSize / audioContext.sampleRate)));
                function draw() {
                    if (!recorder || recorder.state !== 'recording') return;
                    analyser.getByteFrequencyData(frequencies);
                    bars.forEach((bar, i) => {
                        const start = 1 + Math.floor(i * (maxBin - 1) / bars.length);
                        const end = 1 + Math.floor((i + 1) * (maxBin - 1) / bars.length);
                        let peak = 0; for (let bin = start; bin < end; bin++) peak = Math.max(peak, frequencies[bin]);
                        bar.style.setProperty('--voice-level', String(.18 + .82 * peak / 255));
                    });
                    frame = requestAnimationFrame(draw);
                }
                draw();
            } catch (_) { stopSpectrum(); }
        }
        button.addEventListener('click', async () => {
            if (recorder && recorder.state === 'recording') {
                recorder.stop(); recorder.stream.getTracks().forEach(track => track.stop());
                stopSpectrum(); button.classList.remove('is-recording');
                button.setAttribute('aria-pressed', 'false');
                return;
            }
            status.textContent = '';
            let stream;
            try {
                stream = await navigator.mediaDevices.getUserMedia({audio: true});
                recorder = new MediaRecorder(stream); chunks = [];
                recorder.ondataavailable = event => { if (event.data.size) chunks.push(event.data); };
                recorder.onstop = async () => {
                    button.disabled = true; button.classList.add('is-transcribing');
                    button.setAttribute('aria-busy', 'true'); button.setAttribute('aria-label', 'Transcription en cours');
                    status.textContent = 'Transcription en cours…';
                    try {
                        const blob = new Blob(chunks, {type: recorder.mimeType || 'audio/webm'});
                        if (!blob.size) throw new Error('Aucun son enregistré. Vérifiez votre microphone.');
                        const data = new FormData(); data.append('audio', blob, 'recording.webm');
                        data.append('language', localStorage.getItem('preferred_language') || 'fr');
                        const response = await fetch('/api/voice/transcribe/', {method: 'POST', body: data});
                        const result = await response.json();
                        if (!response.ok || result.status !== 'success' || !result.text) throw new Error(result.error || result.message || 'Aucune parole reconnue. Réessayez.');
                        input.value = result.text; input.dispatchEvent(new Event('input', {bubbles: true}));
                        status.textContent = ''; input.focus();
                    } catch (error) { status.textContent = error.message || 'Transcription indisponible.'; }
                    finally {
                        button.disabled = false; button.classList.remove('is-transcribing');
                        button.setAttribute('aria-busy', 'false'); button.setAttribute('aria-label', 'Entrée vocale');
                    }
                };
                recorder.start(); button.classList.add('is-recording');
                button.setAttribute('aria-pressed', 'true'); button.setAttribute('aria-label', 'Arrêter l’enregistrement');
                status.textContent = 'Enregistrement en cours…'; spectrum(stream);
            } catch (error) {
                if (stream) stream.getTracks().forEach(track => track.stop());
                stopSpectrum(); status.textContent = 'Accès au microphone impossible. Vérifiez les autorisations du navigateur.';
            }
        });
    }
    window.CompactChat = {setBusy};
    document.addEventListener('DOMContentLoaded', () => document.querySelectorAll('[data-compact-voice]').forEach(setupVoice));
})();
