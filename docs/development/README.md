# Development

Use Python 3.12.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
alembic upgrade head
pytest -q
ruff check .
python -m compileall -q app connectors migrations mcp_server.py
uvicorn app.main:app --reload --port 8080
```

Run a worker separately:

```bash
python -m app.worker
```

## Change requirements

- Keep PostgreSQL and SQLite behavior compatible.
- Add migrations for model changes.
- Scope every data-bearing query and idempotency check by tenant.
- Keep queued payloads bounded and free of credentials.
- Keep connectors metadata-first and preserve opaque cursors.
- Keep OpenSearch derived and rebuildable.
- Keep evidence bounded and outside the relational database.
- Add deterministic tests without live provider calls.
- Update user, API, architecture, security, connector, deployment, and release documentation when behavior changes.

Policy definitions under `policies/` require an identifier, version, match conditions, decision, reason, risk score, controls, matching tests, and non-matching tests.
