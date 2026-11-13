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

### Choix du modèle

`LLM_PROVIDER=auto` (valeur par défaut) sélectionne LangChain Ollama si
`DEBUG=True`, et Gemini via `langchain-google-genai` si `DEBUG=False`. Tous les appels de génération,
y compris les recherches, articles et publications communautaires, suivent ce choix.

Pour tester Gemini localement, ajoutez dans votre fichier `.env` :

```dotenv
LLM_PROVIDER=gemini
GEMINI_MODEL=gemini-2.5-flash
GEMINI_API_KEY=votre-cle-google
```

Installez les dépendances avec `pip install -r requirements.txt`, puis redémarrez
Django. Remettez `LLM_PROVIDER=auto` pour utiliser Ollama en développement.
En production, configurez `DEBUG=False`, `LLM_PROVIDER=auto` et
`GEMINI_API_KEY` dans les variables d'environnement de l'hébergeur.
Ne placez jamais la clé dans le code ou GitHub. La configuration se trouve dans
`drc_gov_agent/settings.py`, et le client Gemini dans `apps/rag_engine/gemini.py`.
Les embeddings et la transcription vocale conservent leur configuration séparée.

Ce dépôt contient le code d'une application Django. GitHub Pages ne peut pas
exécuter son serveur Python. Utilisez un hébergeur compatible avec Django et
configurez la clé Gemini dans les variables d'environnement du serveur.

En production, définissez un `DJANGO_SECRET_KEY` unique, `DEBUG=False` et
`ALLOWED_HOSTS` avec votre domaine. Configurez également la base de données,
les fichiers statiques, HTTPS et les services requis par votre déploiement.

Les secrets, bases locales, modèles téléchargés et caches sont exclus du dépôt.
