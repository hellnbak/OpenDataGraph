# Contributing

Thank you for helping build an open data intelligence layer for enterprise AI.

1. Open an issue describing the problem and proposed behavior.
2. Create a focused branch and include tests for behavior changes.
3. Run `pytest -q` and `ruff check .` before opening a pull request.
4. Do not commit credentials, real customer data, proprietary schemas, or copied vendor code.
5. Connector pull requests must document required permissions, pagination, rate limits, timestamp semantics, and whether content is retrieved.

Please keep destructive data actions out of the core project. Lifecycle findings should remain advisory until explicit workflow, authorization, and safety controls exist.
