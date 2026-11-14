"""Export local history, then import into an empty Railway database/Chroma volume.

Connection secrets are read from .env, never command-line arguments or printed.
Run --help for commands. Export files contain private history; do not publish them.
"""
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import sys
from urllib.parse import parse_qs, unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from dotenv import load_dotenv

load_dotenv(ROOT / '.env', override=False, encoding='utf-8-sig')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'drc_gov_agent.settings')


def snapshot(source, destination):
    with sqlite3.connect(source.resolve().as_uri() + '?mode=ro', uri=True) as src:
        with sqlite3.connect(destination) as dst:
            src.backup(dst)
            if dst.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                raise RuntimeError('SQLite backup integrity check failed.')


def django_setup(database):
    from django.conf import settings
    settings.DATABASES = {'default': database}
    settings.DB_ENGINE = 'postgres' if database['ENGINE'].endswith('postgresql') else 'sqlite'
    import django
    django.setup()


def export_data(destination):
    destination.mkdir(parents=True, exist_ok=False)
    backup = destination / 'source.sqlite3'
    snapshot(ROOT / 'db.sqlite3', backup)
    django_setup({'ENGINE': 'django.db.backends.sqlite3', 'NAME': str(backup)})
    from django.core.management import call_command
    fixture = destination / 'django-data.json'
    with fixture.open('w', encoding='utf-8') as stream:
        call_command('dumpdata', all=True, natural_foreign=True,
                     exclude=['contenttypes', 'auth.permission'], stdout=stream, verbosity=0)
    rows = json.loads(fixture.read_text(encoding='utf-8'))
    counts = dict(sorted(Counter(row['model'] for row in rows).items()))

    # Read Chroma from a private copy, so Chroma initialization cannot change the source.
    source = Path(os.environ.get('CHROMA_PERSIST_DIRECTORY', ROOT / 'chroma_db'))
    collections = []
    if (source / 'chroma.sqlite3').exists():
        copied = destination / 'chroma-snapshot'
        shutil.copytree(source, copied, ignore=shutil.ignore_patterns('*.sqlite3', '*.sqlite3-wal', '*.sqlite3-shm'))
        snapshot(source / 'chroma.sqlite3', copied / 'chroma.sqlite3')
        import chromadb
        client = chromadb.PersistentClient(path=str(copied))
        for collection in client.list_collections():
            coll = client.get_collection(collection.name)
            result = coll.get(include=['documents', 'metadatas', 'embeddings'])
            embeddings = result.get('embeddings')
            collections.append({'name': coll.name, 'metadata': coll.metadata,
                                'ids': result['ids'], 'documents': result['documents'],
                                'metadatas': result['metadatas'],
                                'embeddings': embeddings.tolist() if embeddings is not None else None})
    chroma_file = destination / 'chroma-data.json'
    chroma_file.write_text(json.dumps(collections, ensure_ascii=False), encoding='utf-8')
    manifest = {'created_at': datetime.now(timezone.utc).isoformat(), 'django_counts': counts,
                'chroma_counts': {c['name']: len(c['ids']) for c in collections},
                'sha256': {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in (fixture, chroma_file)}}
    (destination / 'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    print(json.dumps(manifest, indent=2))
    print('Export saved to', destination)


def verify_export(source):
    manifest = json.loads((source / 'manifest.json').read_text(encoding='utf-8'))
    for name, checksum in manifest['sha256'].items():
        if hashlib.sha256((source / name).read_bytes()).hexdigest() != checksum:
            raise RuntimeError('Export checksum mismatch: ' + name)
    return manifest


def import_database(source):
    manifest = verify_export(source)
    url = os.environ.get('RAILWAY_DATABASE_URL', '')
    if not url:
        raise RuntimeError('Set RAILWAY_DATABASE_URL to the Railway DATABASE_PUBLIC_URL in .env first.')
    parts = urlsplit(url)
    if parts.scheme not in ('postgres', 'postgresql') or not parts.hostname or not parts.path.strip('/'):
        raise RuntimeError('RAILWAY_DATABASE_URL must be a PostgreSQL connection URL.')
    django_setup({'ENGINE': 'django.db.backends.postgresql', 'NAME': unquote(parts.path.lstrip('/')),
                  'USER': unquote(parts.username or ''), 'PASSWORD': unquote(parts.password or ''),
                  'HOST': parts.hostname, 'PORT': str(parts.port or 5432),
                  'OPTIONS': {'sslmode': parse_qs(parts.query).get('sslmode', ['require'])[0],
                              'connect_timeout': 15}})
    from django.apps import apps
    from django.core.management import call_command
    from django.db import connection, transaction
    from django.core.management.color import no_style
    models = [m for m in apps.get_models() if m._meta.label_lower not in
              ('contenttypes.contenttype', 'auth.permission')]
    with connection.cursor() as cursor:
        tables = connection.introspection.table_names()
        for model in models:
            table = model._meta.db_table
            if table in tables:
                cursor.execute('SELECT EXISTS (SELECT 1 FROM ' + connection.ops.quote_name(table) + ')')
                if cursor.fetchone()[0]:
                    raise RuntimeError('Import refused: destination already contains data in ' + table)
        cursor.execute('CREATE EXTENSION IF NOT EXISTS vector')
    call_command('migrate', interactive=False, verbosity=0)
    with transaction.atomic():
        # Check again after migrations; importing never overwrites existing history.
        for model in models:
            if model._base_manager.exists():
                raise RuntimeError('Import refused: destination is not empty: ' + model._meta.label_lower)
        call_command('loaddata', str(source / 'django-data.json'), verbosity=0)
        for label, expected in manifest['django_counts'].items():
            actual = apps.get_model(label)._base_manager.count()
            if actual != expected:
                raise RuntimeError(f'Count mismatch for {label}: {actual} != {expected}')
        with connection.cursor() as cursor:
            for sql in connection.ops.sequence_reset_sql(no_style(), models):
                cursor.execute(sql)
    print('PostgreSQL import complete; all exported model counts verified.')


def import_chroma(source, destination):
    manifest = verify_export(source)
    import chromadb
    client = chromadb.PersistentClient(path=str(destination.resolve()))
    if client.list_collections():
        raise RuntimeError('Chroma import refused: destination already has collections.')
    collections = json.loads((source / 'chroma-data.json').read_text(encoding='utf-8'))
    for item in collections:
        coll = client.create_collection(name=item['name'], metadata=item['metadata'])
        for offset in range(0, len(item['ids']), 100):
            end = offset + 100
            kwargs = {'ids': item['ids'][offset:end]}
            for key in ('documents', 'metadatas', 'embeddings'):
                if item.get(key) is not None:
                    batch = item[key][offset:end]
                    if key != 'metadatas' or any(batch):
                        kwargs[key] = batch
            coll.add(**kwargs)
        if coll.count() != manifest['chroma_counts'][item['name']]:
            raise RuntimeError('Chroma count mismatch: ' + item['name'])
    print('Chroma import complete; all collection counts verified.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['export', 'import-db', 'import-chroma'])
    parser.add_argument('directory', type=Path, help='Private export directory (keep out of Git)')
    parser.add_argument('--chroma-destination', type=Path, help='Empty persistent Chroma directory')
    args = parser.parse_args()
    if args.action == 'export':
        export_data(args.directory.resolve())
    elif args.action == 'import-db':
        import_database(args.directory.resolve())
    else:
        if not args.chroma_destination:
            parser.error('--chroma-destination is required for import-chroma')
        import_chroma(args.directory.resolve(), args.chroma_destination)


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        # Connection exceptions can contain credentials. Print only actionable local errors.
        if isinstance(exc, (RuntimeError, FileExistsError)):
            print(str(exc), file=sys.stderr)
        else:
            print('Transfer failed (' + type(exc).__name__ + '); check connection and schema configuration.', file=sys.stderr)
        sys.exit(1)
