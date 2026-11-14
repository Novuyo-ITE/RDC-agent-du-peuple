# install.ps1 — One-shot CPU-only install for Windows PowerShell
# Usage: .\install.ps1
# No Docker required. Works on any machine with Python 3.11+.

Write-Host "=== Installing CPU-only PyTorch first ===" -ForegroundColor Cyan
pip install torch --index-url https://download.pytorch.org/whl/cpu

Write-Host "`n=== Installing all other requirements ===" -ForegroundColor Cyan
pip install -r requirements.txt

Write-Host "`n=== Running migrations ===" -ForegroundColor Cyan
python manage.py migrate

Write-Host "`n=== Fetching real DRC news ===" -ForegroundColor Cyan
python manage.py fetch_drc_news

Write-Host "`nDone! Start with: python manage.py runserver" -ForegroundColor Green

