# Governance Frameworks

OpenDataGraph v1.9 includes an evidence-coverage mapping for NIST AI RMF 1.0 under `policies/frameworks`. The mapping connects framework outcomes to OpenDataGraph metadata evidence such as AI inventory, lineage, authorization receipts, enforcement events, telemetry, policy bundles, and rollouts.

## APIs

- `GET /api/v1/governance/frameworks` requires `read-only`.
- `POST /api/v1/governance/frameworks/{framework_id}/coverage` requires `auditor` and accepts a 1–366 day window.

Each control reports the expected evidence types, tenant-scoped record counts, and `evidenced` or `gap` state. Coverage is intentionally strict: every mapped evidence type must have evidence in the selected window, except inventory types without a source timestamp, which report current tenant state.

## Interpretation

Coverage reports answer whether OpenDataGraph has the mapped operational evidence. They do not assess evidence quality, organizational effectiveness, legal applicability, control design, or risk acceptance, and they do not certify compliance. Reviewers must validate each mapping and underlying record against the organization’s own scope and NIST guidance.

Framework YAML is versioned application configuration. Changes require stable identifiers, source attribution, review, tests, and release notes. Do not silently reinterpret historical reports after changing a mapping.
