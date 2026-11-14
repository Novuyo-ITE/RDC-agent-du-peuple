# RDC Agent du Peuple

Assistant numérique multilingue officiel pour la République Démocratique du Congo.
Construit avec **Django 5**, **LangChain**, **Ollama** (local) ou **Gemini** (cloud), et un moteur RAG.

---

## Démarrage local (aucun Docker requis)

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
# Éditez .env selon vos besoins (voir section Configuration ci-dessous)
python manage.py migrate
python manage.py runserver
```

L'application démarre avec **SQLite** si PostgreSQL n'est pas détecté — aucune base externe requise pour commencer.

---

## Pourquoi aucun Docker n'est nécessaire

Le `docker-compose.yml` fourni démarrait uniquement **PostgreSQL** et **Redis**.
Ces deux services sont **optionnels** grâce aux bascules automatiques intégrées dans `settings.py` :

| Service | Avec Docker | Sans Docker |
|---|---|---|
| **Base de données** | PostgreSQL + pgvector | SQLite (auto-détecté) |
| **WebSocket / Channels** | Redis channel layer | InMemoryChannelLayer |
| **Cache** | Redis | LocMemCache (fichier local) |
| **Celery** | Redis broker | Pas de worker Celery nécessaire |

La bascule est automatique : si PostgreSQL répond sur le port 5432, il est utilisé ; sinon SQLite prend le relais. Même logique pour Redis.

---

## Configuration

Copiez `.env.example` en `.env` et adaptez :

```dotenv
# Clé secrète Django — changez-la en production !
DJANGO_SECRET_KEY=une-cle-secrete-tres-longue

# LLM : auto → Ollama en dev (DEBUG=True), Gemini en prod (DEBUG=False)
LLM_PROVIDER=auto
GEMINI_API_KEY=votre-cle-google

# Modèle Ollama pour le développement local
OLLAMA_MODEL=qwen2.5:7b

# Voix / transcription (CPU par défaut, pas de GPU requis)
WHISPER_DEVICE=cpu
WHISPER_COMPUTE=int8
```

---

## Déploiement cloud (Railway / Render / Fly.io / VPS)

### Variables d'environnement à définir sur le serveur

```dotenv
DEBUG=False
LLM_PROVIDER=gemini          # ou auto (Gemini sera sélectionné car DEBUG=False)
GEMINI_API_KEY=votre-cle
DJANGO_SECRET_KEY=cle-longue-et-unique
ALLOWED_HOSTS=votre-domaine.com
DB_ENGINE=sqlite              # ou omettez si Postgres est fourni par la plateforme
WHISPER_DEVICE=cpu
WHISPER_COMPUTE=int8
EMBEDDING_ALLOW_DOWNLOAD=False
```

### Commande de démarrage

```bash
python manage.py migrate
python manage.py collectstatic --noinput
python manage.py fetch_drc_news          # peuple les actualités réelles
daphne drc_gov_agent.asgi:application --port $PORT --bind 0.0.0.0
```

### Notes importantes sur `requirements.txt`

- **`torch`** est épinglé via `--extra-index-url https://download.pytorch.org/whl/cpu`
  → Installe la version **CPU-only** (~220 MB au lieu de 2 GB pour CUDA).
- **`faster-whisper`** fonctionne en CPU avec `int8` — aucun CUDA requis.
- **`chromadb`** est un wheel Python pur — pas de dépendances binaires CUDA.
- **`psycopg[binary]`** et **`pgvector`** s'installent sans erreur sur les hôtes sans Postgres ; ils ne sont activés que si la base est détectée.

### Sur un serveur avec GPU (optionnel)

Ajoutez dans `.env` pour profiter du GPU :

```dotenv
WHISPER_DEVICE=cuda
WHISPER_COMPUTE=float16
WHISPER_MODEL=medium
```

Et remplacez la ligne `torch` dans `requirements.txt` par la version CUDA appropriée (voir https://pytorch.org/get-started/locally/).

---

## Architecture

```
drc_gov_agent/
├── apps/
│   ├── rag_engine/      # RAG, LLM, récupération des actualités, modèles
│   ├── web_ui/          # Vues Django, templates, navigation
│   ├── voice/           # Transcription audio (faster-whisper, CPU-safe)
│   └── scraper/         # Scraping de sources officielles
├── static/              # JS, CSS, icônes Lucide locaux
├── drc_gov_agent/       # settings.py, urls.py, wsgi.py, asgi.py
├── requirements.txt     # Dépendances CPU-only
├── .env.example         # Template de configuration
└── manage.py
```
