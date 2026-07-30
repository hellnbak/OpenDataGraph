# Development

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pytest -q
ruff check .
python -m compileall -q app connectors mcp_server.py
uvicorn app.main:app --reload --port 8080
```

Keep connectors metadata-first, normalize records through `AssetRecord`, preserve cursor semantics, and record safe errors without credentials. Add tests for classification, policy, authorization, event, and relationship behavior. Never include customer data or secrets in fixtures.

Policy definitions live in `policies/`. A policy must include an identifier, version, match conditions, decision, reason, risk score, and controls.
