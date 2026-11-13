"""Benchmark a local llama.cpp server; save timings, GPU use, and raw answers."""
import json
from pathlib import Path
import subprocess
import time
import requests

BASE = 'http://127.0.0.1:11434'
OUT = Path(__file__).resolve().parents[1] / 'output' / 'lingala-q8-benchmark.json'
PROMPTS = [
    ('greeting', 'Mbote! Omibengisa nani? Yanola na Lingala.'),
    ('instruction', 'Tanga biloko misato oyo moto akoki komema na kelasi. Pesa liste ya biloko misato kaka, na Lingala.'),
    ('grounded', 'Na mokanda oyo: Marie azali na mbula 25. Afandaka na Matadi. Azali moteki. Motuna: Marie afandaka na engumba nini? Yanola na nkombo ya engumba kaka.'),
    ('arithmetic', 'Nazali na manga 3. Babakisi ngai manga 2. Nazali na manga boni sikoyo?'),
    ('translation', 'Traduis en lingala : Bonjour, comment allez-vous aujourd’hui ?'),
    ('explanation', 'Loba na Lingala: mpo na nini ezali malamu kotanga mikanda?'),
]

def gpu():
    return subprocess.check_output(['nvidia-smi', '--query-gpu=memory.used,utilization.gpu', '--format=csv,noheader,nounits'], text=True).strip()

def main():
    for _ in range(180):
        try:
            if requests.get(BASE + '/api/tags', timeout=2).ok:
                break
        except requests.RequestException:
            pass
        time.sleep(2)
    else:
        raise RuntimeError('Server did not become ready')
    results = {'backend': 'Ollama CUDA', 'quantization': 'Q8_0', 'context': 8192, 'gpu_before': gpu(), 'cases': []}
    for name, prompt in PROMPTS:
        start = time.perf_counter()
        response = requests.post(BASE + '/api/chat', json={
            'model': 'congo-lingala:q8_0', 'stream': False, 'keep_alive': '10m',
            'messages': [{'role': 'user', 'content': prompt}],
            'options': {'num_ctx': 8192, 'num_predict': 160, 'temperature': 0, 'seed': 42},
        }, timeout=600)
        response.raise_for_status()
        data = response.json()
        row = {'name': name, 'prompt': prompt, 'seconds': time.perf_counter()-start,
               'answer': data['message']['content'],
               'finish_reason': data.get('done_reason'),
               'timings': {k: v for k, v in data.items() if k.endswith(('_duration', '_count'))},
               'gpu': gpu(), 'tokens_per_second': data.get('eval_count', 0) / max(data.get('eval_duration', 1) / 1e9, 1e-9)}
        results['cases'].append(row)
        OUT.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps(row, ensure_ascii=True), flush=True)

if __name__ == '__main__':
    main()
