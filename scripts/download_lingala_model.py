"""Download the gated Lingala weights after `hf auth login` and access approval."""
from pathlib import Path
import argparse
import shutil

from huggingface_hub import HfApi, snapshot_download
from huggingface_hub.errors import GatedRepoError


MODEL_ID = 'Congo-digital-service/Llama-3.1-8B-Instruct-Lingala-QLoRA-merged-v2'
DESTINATION = Path(__file__).resolve().parents[1] / 'models' / 'lingala-llama3.1-8b'


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', type=Path, default=DESTINATION)
    args = parser.parse_args()
    destination = args.directory.resolve()
    destination.mkdir(parents=True, exist_ok=True)
    try:
        info = HfApi().model_info(MODEL_ID, files_metadata=True)
        needed = sum(file.size or 0 for file in info.siblings
                     if not (destination / file.rfilename).is_file())
        if shutil.disk_usage(destination).free < needed + 2 * 1024**3:
            raise SystemExit('Insufficient disk space. Use --directory on a drive with at least 19 GB free.')
        location = snapshot_download(MODEL_ID, local_dir=destination, max_workers=4)
    except GatedRepoError:
        raise SystemExit(
            f'Access required: accept the conditions at https://huggingface.co/{MODEL_ID}, '
            'then run `hf auth login` with an authorized read token and retry this script.'
        )
    print(f'Downloaded Transformers weights to {location}.')
    print('These weights need conversion/import before they can be used by Ollama.')
