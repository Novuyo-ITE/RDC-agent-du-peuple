Les recherches Web du chat principal, du guide Services et du lecteur d’articles
passent par Tavily. La clé `TAVILY_API_KEY` est lue dans `.env` côté Django ; aucune
clé n’est envoyée au navigateur. Une variable d’environnement du processus garde
la priorité sur `.env`. `TAVILY_SEARCH_DEPTH=basic` est la valeur par défaut.

Vérifier la connexion sans imprimer la clé :

```powershell
python manage.py shell -c "from apps.rag_engine.web_search import TavilyDRCSearchTool; print(TavilyDRCSearchTool().search('passeport site:diplomatie.gouv.cd')['status'])"
```

Les huit dossiers relus sont dans `apps/rag_engine/data/service_dossiers.json`.
Ils comprennent les sources, la date de recherche, les conditions, les pièces,
les étapes ordonnées et les accès aux formulaires. Les données sont séparées du
code et importées dans le champ `source_snapshot`, modifiable via le modèle.
Les divergences de tarifs et les accès restreints sont signalés dans les fiches.

```powershell
python manage.py migrate
python manage.py load_service_dossiers
```

L’import exige que les services existent déjà dans le répertoire. Il ne refait
aucune recherche et conserve la date de consultation d’origine. Pour une mise à
jour, consulter les sources officielles, relire les différences, mettre à jour
les références et la date du dossier concerné puis réimporter. Ces dossiers ne
prétendent pas être actualisés automatiquement à chaque modification du site
institutionnel.

`scripts/extract_service_sources.py` récupère les pages de référence via Tavily
Extract et conserve les résultats publics dans `service_research/` (ignoré par
Git). Une extraction qui retourne une page de connexion ne valide pas le contenu
du service. Les constats issus d’une lecture du navigateur ou du catalogue indexé
doivent être relus séparément.

Les boutons « Ouvrir dans cet espace » ouvrent désormais une session navigateur
isolée du portail dans la colonne gauche. Les champs et boutons sont lus dans
la page courante. La saisie, les pièces jointes (10 Mo maximum), la connexion et
le clic sur les boutons réels sont transmis au navigateur du portail. Le citoyen
peut consulter son écran, cliquer, faire défiler et saisir dans le champ actif.
Les cookies et protections CSRF restent ceux du navigateur officiel : aucun
POST reconstruit ni contournement de connexion. Les références d’action empêchent
de rejouer deux fois une même commande de dépôt dans une session.

Le guide peut lire les intitulés des champs de la session active et proposer des
valeurs à partir du brouillon avec Ollama. Les valeurs actuelles, mots de passe,
fichiers et jetons ne sont pas ajoutés automatiquement au contexte IA. Les
propositions sont relues puis reprises par le citoyen avant envoi au formulaire.
L’interface affiche la réponse du portail ; elle ne fabrique aucun récépissé.
Les démarches imposant un guichet, une capture ou une plateforme professionnelle
conservent ces étapes. Une page d’information ne devient pas un formulaire de
dépôt grâce à cette intégration. Certains portails peuvent refuser un navigateur
automatisé ou nécessiter une destination d’authentification/paiement additionnelle.

Installation du navigateur : sur Windows, Edge est utilisé par défaut ; sur
Linux, installer Chromium avec `python -m playwright install chromium`.
`SERVICE_BROWSER_CHANNEL` peut sélectionner un autre navigateur installé.
La session est liée à la session Django, expire après 20 minutes d’inactivité et
est détruite au clic Fermer. Les URL d’ouverture proviennent des ressources du
service ; les navigations sont limitées à leurs domaines et aux widgets de
sécurité reconnus. Les réseaux privés/locaux sont bloqués. Les captures et réponses
portent `Cache-Control: no-store`. Les sessions restent dans le processus serveur
(8 simultanées maximum) : un déploiement à plusieurs workers exige une affinité
de session ou un gestionnaire de navigateurs partagé.

Le modèle d’embeddings est chargé uniquement lorsqu’il existe des fragments de
documents à rechercher. Son initialisation est protégée par verrou et réutilisée
dans le processus ; un échec impose cinq minutes avant une nouvelle tentative.
Par défaut, seuls les fichiers déjà en cache sont utilisés. Activer explicitement
`EMBEDDING_ALLOW_DOWNLOAD=True` pour autoriser le téléchargement d’un modèle absent.
Un redémarrage du processus ou le rechargement Django après modification du code
réinitialise naturellement les objets en mémoire.

Les conversations des actualités et des services rejoignent le même historique
Chroma que le chat principal. Les métadonnées `kind`, `article_id` ou `service_code`
permettent de les rouvrir dans la page appropriée, avec les messages utilisateur
et assistant. Les tours sauvegardés côté serveur prennent priorité sur le contenu
du navigateur lors d’une reprise. Les anciens historiques de l’onglet sont
importés via `/api/rag/sessions/import/` ; leur identifiant de migration est
conservé jusqu’au succès et une reprise d’import n’ajoute pas les tours déjà présents.
