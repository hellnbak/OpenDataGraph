# Development

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pytest -q
ruff check .
uvicorn app.main:app --reload --port 8080
```

Keep connectors metadata-first, normalize records into `DataAsset`, add tests for policy-impacting changes, and never commit credentials or customer data.
