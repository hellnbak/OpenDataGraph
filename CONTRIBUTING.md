# Contributing

Thank you for helping build an open data intelligence layer for enterprise AI.

1. Describe the problem, expected behavior, security impact, and compatibility considerations.
2. Keep changes focused and include tests for behavior changes.
3. Run `pytest -q`, `ruff check .`, and Python compilation before opening a pull request.
4. Never include credentials, real customer data, proprietary schemas, access tokens, or copied vendor code.
5. Connector changes must document permissions, pagination, rate limits, cursor semantics, timestamps, and whether content is retrieved.
6. Policy changes must include an example decision and explain new controls.

Lifecycle findings remain advisory until an explicitly authorized workflow performs an external action.
