const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const template = fs.readFileSync(path.join(__dirname, '../templates/index.html'), 'utf8');
const start = template.indexOf('    async function toggleVoiceRecording()');
const end = template.indexOf('</script>', start);

function classList() {
  const values = new Set();
  return {add(name) { values.add(name); }, remove(name) { values.delete(name); },
    toggle(name, enabled) { enabled ? values.add(name) : values.delete(name); },
    contains(name) { return values.has(name); }};
}

test('shows a live spectrum while recording and a progress ring during transcription', async () => {
  const attributes = {}, levels = [], track = {stopped: false, stop() { this.stopped = true; }};
  let recorder, resolveFetch, tick, disconnected = false, contextClosed = false, frameCancelled = false;
  const bars = Array.from({length: 5}, (_, index) => ({style: {setProperty(name, value) { levels[index] = Number(value); }}}));
  const mic = {classList: classList(), disabled: false, title: '', setAttribute(name, value) { attributes[name] = value; }};
  const input = {value: '', placeholder: ''}, status = {textContent: ''};
  const nodes = {'mic-btn': mic, 'query-input': input, 'voice-transcription-status': status,
    'recording-indicator': {hidden: true}, 'recording-timer': {textContent: ''}};
  const audio = {
    sampleRate: 48000,
    createAnalyser() { return {frequencyBinCount: 128, getByteFrequencyData(values) { values.fill(160); }}; },
    createMediaStreamSource() { return {connect() {}, disconnect() { disconnected = true; }}; },
    close() { contextClosed = true; return Promise.resolve(); },
  };
  class MediaRecorder {
    constructor(stream) { this.stream = stream; recorder = this; }
    start() {}
    stop() {}
  }
  const pending = new Promise(resolve => { resolveFetch = resolve; });
  let responsePromise = pending;
  const context = {window: {AudioContext: function () { return audio; }},
    document: {getElementById: id => nodes[id], querySelectorAll: () => bars},
    navigator: {mediaDevices: {getUserMedia: async () => ({getTracks: () => [track]})}},
    MediaRecorder, Blob, FormData, fetch: () => responsePromise, console,
    requestAnimationFrame: () => 17, cancelAnimationFrame() { frameCancelled = true; },
    setInterval: callback => { tick = callback; return 1; }, clearInterval() {}, alert() { throw Error('unexpected error'); }};
  const prefix = `let isRecording=false, mediaRecorder=null, audioChunks=[], timerInterval=null, secondsElapsed=0;
    let currentLanguage='fr', speechRecognizer=null, recognizedLiveText='';
    let voiceAudioContext=null, voiceAnalyser=null, voiceAudioSource=null, voiceSpectrumFrame=null;
    function applyLanguageUI() { document.getElementById('query-input').placeholder = 'Posez votre question'; }\n`;
  vm.createContext(context);
  vm.runInContext(prefix + template.slice(start, end), context);
  await context.startVoiceRecording();
  recorder.ondataavailable({data: new Blob(['audio'])});
  assert.equal(mic.classList.contains('is-recording'), true);
  assert.equal(mic.classList.contains('has-live-spectrum'), true);
  assert.ok(levels.every(level => level > .18 && level <= 1));
  assert.equal(attributes['aria-pressed'], 'true');
  assert.equal(nodes['recording-indicator'].hidden, false);
  assert.equal(nodes['recording-timer'].textContent, '00:00');
  tick();
  assert.equal(nodes['recording-timer'].textContent, '00:01');
  context.stopVoiceRecording();
  assert.equal(nodes['recording-indicator'].hidden, true);
  assert.equal(track.stopped, true);
  assert.equal(disconnected, true);
  assert.equal(contextClosed, true);
  assert.equal(frameCancelled, true);
  const transcription = recorder.onstop();
  assert.equal(mic.classList.contains('is-transcribing'), true);
  assert.equal(mic.disabled, true);
  assert.equal(status.textContent, 'Transcription en cours…');
  assert.equal(input.placeholder, 'Transcription en cours…');
  resolveFetch({ok: true, json: async () => ({status: 'success', text: 'Bonjour'})});
  await transcription;
  assert.equal(input.value, 'Bonjour');
  assert.equal(input.placeholder, 'Posez votre question');
  assert.equal(mic.classList.contains('is-transcribing'), false);
  assert.equal(mic.disabled, false);
  assert.equal(status.textContent, '');

  responsePromise = Promise.resolve({ok: true, json: async () => ({status: 'error', error: 'Moteur indisponible'})});
  await context.startVoiceRecording();
  assert.equal(nodes['recording-timer'].textContent, '00:00');
  recorder.ondataavailable({data: new Blob(['audio'])});
  context.stopVoiceRecording();
  await recorder.onstop();
  assert.equal(input.value, 'Bonjour');
  assert.equal(status.textContent, 'Moteur indisponible');
  assert.equal(mic.disabled, false);
});
