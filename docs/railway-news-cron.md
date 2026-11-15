# News updates independent of visitors

Create a **separate Railway service**, named `news-refresh`, from this repository.
Set its config file path to `/railway-news-cron.json`.
Do not apply this cron config to the existing web service.

The job runs every 15 minutes, imports new articles into the database and exits.
One failed source does not prevent other sources from importing. Existing articles
are preserved. Railway skips overlapping scheduled runs automatically.

## Shared production database

Copy the web service database variables to the job through Railway references:
`DB_ENGINE=postgres`, `POSTGRES_HOST`, `POSTGRES_PORT`, `POSTGRES_DB`,
`POSTGRES_USER`, `POSTGRES_PASSWORD`. Include the Django settings/secrets required
by the same application. Both services must use the SAME persistent PostgreSQL
database. A separate SQLite file in the cron container will not update the website.

## Activation and verification

1. Deploy the separate service with the config above.
2. Trigger its first cron run from Railway; check logs for per-source counts.
3. Confirm articles appear at `/accueil/` without opening `/actualites/` first.
4. Leave the site closed for a scheduled interval and verify a new run appears in
   Railway Cron Runs. Articles remain readable even if a later source is offline.

This file prepares configuration; it does not provision or activate a Railway service.
Reference: https://docs.railway.com/cron-jobs
