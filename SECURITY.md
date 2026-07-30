# Security Policy

## Supported versions

Only the latest development release is supported during the preview phase.

## Reporting vulnerabilities

Do not disclose suspected vulnerabilities in a public issue. Before publishing the repository, replace this paragraph with a monitored private security-reporting address or enable GitHub private vulnerability reporting.

## V1 deployment warning

This preview is designed for local testing and screenshots. It does not yet include authentication, tenant isolation, production secret management, request throttling, or hardened network defaults. Do not expose it directly to the public internet or connect it to sensitive production sources without adding those controls.

## Credential handling

The service uses standard AWS credential resolution and does not persist AWS keys. Prefer short-lived, least-privilege roles. Never place credentials in `.env`, screenshots, sample payloads, or Git history.
