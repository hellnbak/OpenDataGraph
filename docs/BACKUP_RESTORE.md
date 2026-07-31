# Backup and Restore

OpenDataGraph v1.4 includes database and local-evidence backup tooling.

## Backup

```bash
python -m app.operations backup --output /secure/backup/location
```

SQLite uses the online backup API. PostgreSQL uses `pg_dump` in custom format and passes passwords through `PGPASSWORD`, not command arguments. Local evidence is copied into the backup directory. S3-compatible evidence remains external and must be protected by bucket versioning, retention, and independent backup policy.

Each backup includes `manifest.json` with format, application version, backend, database filename, evidence mode, and timestamp. Backups never include API keys or connector secret files.

## Restore

Stop API and worker processes before restore:

```bash
python -m app.operations restore --source /secure/backup/location --force
```

Restore is destructive and requires `--force`. PostgreSQL restore uses `pg_restore --clean --if-exists`. After restore, run `alembic upgrade head`, start API and worker processes, reindex OpenSearch, and verify `/ready`.

Test recovery regularly in an isolated environment. Encrypt backup media and restrict access.
