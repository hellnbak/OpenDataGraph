# Classification

The v1.1 pipeline produces:

- sensitivity: Public, Internal, Confidential, or Restricted
- labels such as Secrets, PII, Financial, Health, Source Code, or Legal
- business domain
- explanation
- confidence
- review requirement

## Inputs

Classification can use filename, path, MIME type, provider metadata, and an explicitly bounded sample. Deterministic patterns detect common credential, PII, financial, healthcare, legal, and source-code signals.

When `ODG_CLASSIFICATION_MODE` is `ollama` or `hybrid`, a local model may enrich the deterministic baseline. Hybrid mode falls back safely if the model is unavailable.

## Review queue

Results below `ODG_CLASSIFICATION_REVIEW_THRESHOLD` enter the classification review queue. An analyst can:

- approve the original result
- reject the result
- correct sensitivity and labels

A correction records the reviewer and resolution time and updates the catalog asset with full confidence.

## Privacy

Sampled content is optional and should remain disabled unless the organization has approved source scope, byte limits, processing location, retention, and access controls.
