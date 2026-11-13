# RDC-agent-du-peuple

Assistant numérique multilingue pour la République démocratique du Congo,
construit avec Django, une recherche documentaire et Ollama.

## Démarrage local

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
python manage.py migrate
python manage.py runserver
```

Installez Ollama et téléchargez le modèle configuré avec
`ollama pull qwen2.5:7b`. Configurez les clés et paramètres dans `.env`.
Les fonctionnalités de recherche web utilisent `TAVILY_API_KEY`.
Les modèles de transcription et d'embeddings sont configurés séparément.

## Hébergement

Ce dépôt contient le code d'une application Django. GitHub Pages ne peut pas
exécuter son serveur Python. Utilisez un hébergeur compatible avec Django et
configurez un service Ollama accessible depuis le serveur.

En production, définissez un `DJANGO_SECRET_KEY` unique, `DEBUG=False` et
`ALLOWED_HOSTS` avec votre domaine. Configurez également la base de données,
les fichiers statiques, HTTPS et les services requis par votre déploiement.

Les secrets, bases locales, modèles téléchargés et caches sont exclus du dépôt.
