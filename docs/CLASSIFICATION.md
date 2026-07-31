# Classification

The v1.6 pipeline produces sensitivity, labels, business domain, explanation, confidence, and review requirements.

## Inputs

Classification can use filename, path, MIME type, provider metadata, and an explicitly bounded sample. Deterministic patterns detect common credential, PII, financial, healthcare, legal, and source-code signals.

When `ODG_CLASSIFICATION_MODE` is `ollama` or `hybrid`, a local model may enrich the deterministic baseline. Hybrid mode falls back safely if the model is unavailable.

## Review queue

Results below `ODG_CLASSIFICATION_REVIEW_THRESHOLD` enter a tenant-scoped review queue. An analyst can approve, reject, or correct sensitivity and labels. Corrections record reviewer and resolution time, update the catalog, and refresh the derived search document.

## Privacy

Sampled content is optional and should remain disabled unless source scope, byte limits, processing location, retention, and access controls are approved. Samples are not persisted in assets, connector runs, jobs, search documents, logs, traces, or graph edges.
