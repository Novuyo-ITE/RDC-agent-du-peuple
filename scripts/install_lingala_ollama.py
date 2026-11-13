"""Import completed Hugging Face weights, smoke test, then enable Lingala routing.

Usage: python scripts/install_lingala_ollama.py D:/AI-models/lingala-llama3.1-8b --wait
The download must run separately. No Hugging Face credential is stored here.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import time

import requests


MODEL_NAME = 'congo-lingala:8b'
PROJECT = Path(__file__).resolve().parents[1]


def install(directory, wait=False, gguf=None):
    required = ['model.safetensors', 'config.json', 'tokenizer.json', 'tokenizer_config.json']
    deadline = time.monotonic() + 12 * 3600
    while not all((directory / name).is_file() for name in required):
        if not wait or time.monotonic() > deadline:
            raise RuntimeError('Model download is incomplete; finish the download and rerun this script.')
        time.sleep(15)
    # Hugging Face publishes the final weight filename only after download completion.
    if gguf is None or not gguf.is_file():
        raise RuntimeError('Supply --gguf with the converted and quantized GGUF file for Windows Ollama.')
    print('Importing quantized GGUF into Ollama.', flush=True)
    modelfile = directory / 'Modelfile'
    modelfile.write_text(
        f'FROM "{gguf.as_posix()}"\n'
        'TEMPLATE """{{- range .Messages }}<|start_header_id|>{{ .Role }}<|end_header_id|>\n\n{{ .Content }}<|eot_id|>{{- end }}<|start_header_id|>assistant<|end_header_id|>\n\n"""\n'
        'PARAMETER stop "<|eot_id|>"\n'
        'PARAMETER stop "<|end_of_text|>"\n'
        'PARAMETER stop "<|start_header_id|>"\n'
        'PARAMETER num_ctx 8192\n'
        'PARAMETER temperature 0.2\n', encoding='utf-8')
    env = os.environ.copy()
    scratch = directory / 'tmp'
    scratch.mkdir(exist_ok=True)
    env.update(TMP=str(scratch), TEMP=str(scratch))
    subprocess.run(['ollama', 'create', MODEL_NAME, '-f', str(modelfile)], check=True, env=env)
    base_url = os.environ.get('OLLAMA_BASE_URL', 'http://127.0.0.1:11434').rstrip('/')
    response = requests.post(base_url + '/api/chat', json={
        'model': MODEL_NAME,
        'messages': [{'role': 'user', 'content': 'Mbote! Omibengisa nani? Yanola na Lingala.'}],
        'stream': False, 'keep_alive': 0,
        'options': {'num_ctx': 2048, 'num_predict': 80},
    }, timeout=600)
    response.raise_for_status()
    answer = response.json().get('message', {}).get('content', '').strip()
    if not answer:
        raise RuntimeError('Model returned no text. Lingala routing has not been enabled.')
    print('Smoke response: ' + answer, flush=True)
    env_file = PROJECT / '.env'
    lines = env_file.read_text(encoding='utf-8').splitlines()
    lines = [line for line in lines if not line.startswith('OLLAMA_LINGALA_MODEL=')]
    lines.append('OLLAMA_LINGALA_MODEL=' + MODEL_NAME)
    env_file.write_text('\n'.join(lines) + '\n', encoding='utf-8')
    status = {'model': MODEL_NAME, 'status': 'ready', 'smoke_response': answer,
              'action': 'Restart Django to load OLLAMA_LINGALA_MODEL.'}
    (PROJECT / 'output' / 'lingala-install-status.json').write_text(
        json.dumps(status, ensure_ascii=False, indent=2), encoding='utf-8')
    print('Lingala enabled in .env. Restart Django to apply.', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    parser.add_argument('--wait', action='store_true')
    parser.add_argument('--gguf', type=Path, required=True)
    args = parser.parse_args()
    try:
        install(args.directory.resolve(), args.wait, args.gguf.resolve())
    except Exception as exc:
        print(f'Installation failed; routing was not enabled: {exc}', flush=True)
        raise
