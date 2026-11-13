"""Finish the current GGUF conversion, quantize it, and install it in Ollama."""
import argparse
from pathlib import Path
import subprocess
import sys
import time


PROJECT = Path(__file__).resolve().parents[1]


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', type=Path, default=Path('D:/AI-models/lingala-llama3.1-8b'))
    parser.add_argument('--quantizer', type=Path, default=Path('D:/AI-models/tools/bin/llama-quantize.exe'))
    args = parser.parse_args()
    log = PROJECT / 'output' / 'lingala-convert.log'
    deadline = time.monotonic() + 12 * 3600
    print('Waiting for successful GGUF conversion.', flush=True)
    while True:
        raw = log.read_bytes() if log.exists() else b''
        encoding = 'utf-16' if raw.startswith((b'\xff\xfe', b'\xfe\xff')) else 'utf-8'
        status = raw.decode(encoding, errors='replace')
        if 'Model successfully exported to' in status:
            break
        if 'Traceback (most recent call last)' in status or time.monotonic() > deadline:
            raise SystemExit('Conversion failed or timed out. See output/lingala-convert.log.')
        time.sleep(15)
    source = args.directory / 'lingala-f16.gguf'
    target = args.directory / 'lingala-Q4_K_M.gguf'
    print('Conversion finished. Quantizing to Q4_K_M.', flush=True)
    subprocess.run([str(args.quantizer), str(source), str(target), 'Q4_K_M'], check=True)
    print('Quantization finished. Importing and testing in Ollama.', flush=True)
    subprocess.run([sys.executable, str(PROJECT / 'scripts' / 'install_lingala_ollama.py'),
                    str(args.directory), '--gguf', str(target)], check=True)
