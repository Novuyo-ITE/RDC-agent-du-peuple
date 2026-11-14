#!/usr/bin/env bash
# install.sh — One-shot CPU-only install for Linux/macOS/cloud build runners
# Usage: bash install.sh
# No Docker required. Works on Railway, Render, Fly.io, standard VPS.

set -e

echo "=== Installing CPU-only PyTorch first ==="
pip install torch --index-url https://download.pytorch.org/whl/cpu

echo ""
echo "=== Installing all other requirements ==="
pip install -r requirements.txt

echo ""
echo "=== Running migrations ==="
python manage.py migrate

echo ""
echo "=== Collecting static files ==="
python manage.py collectstatic --noinput

echo ""
echo "=== Fetching real DRC news ==="
python manage.py fetch_drc_news || echo "News fetch skipped (network may not be available at build time)"

echo ""
echo "Done! Start with: daphne drc_gov_agent.asgi:application"

