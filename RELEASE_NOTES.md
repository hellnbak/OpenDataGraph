# OpenDataGraph v1.7.0

OpenDataGraph v1.7 adds assurance and extensibility controls: cryptographically signed governance evidence, connector capability governance, major-cloud workload exchange, Google Cloud Storage and Azure Blob export sinks, ownership escalation and trend analytics, and comparative performance baselines.

All v1.1 through v1.6 capabilities remain part of the platform. The README lists cumulative platform capabilities separately from release-specific additions.

## Signed governance evidence

Governance evidence package format version 2 adds a canonical manifest, whole-payload SHA-256, per-section digests, generator identity, and an assurance envelope. Workers can sign with mounted Ed25519 keys, AWS KMS, or Sigstore keyless identities. Signing credentials remain external references.

Verification first recomputes payload and section digests, then validates the signature, then evaluates the signer against a separate trust profile. The API and `python -m app.evidence_verify` report cryptographic validity separately from configured trust. Existing storage-level digest checks remain in place.

## Connector capability governance

Connector SDK v2 introduces versioned manifests for permissions, egress, content access, pagination, cursor behavior, rate-limit handling, timestamp provenance, public-access interpretation, and destructive-action declarations. Runs record connector version, manifest digest, and capability policy version.

A central registry preserves all built-in connectors and supports explicitly allowlisted Python entry-point plugins. Deployment policy and versioned tenant policy can deny connector types, content-access levels, egress hosts, destructive behavior, non-incremental or non-opaque cursors, and oversized permission declarations. `python -m connectors.conformance` validates installed manifests without provider calls.

Plugins remain trusted in-process code and require ordinary software supply-chain review; capability policy is not a sandbox.

## Cloud workload exchange and export sinks

Named workload exchange profiles read a referenced subject token only when needed and issue temporary AWS STS, Azure federated client, or Google Cloud STS credentials for at most one hour. Subject and returned credentials are never persisted or returned by profile-test APIs.

S3 sinks can use an AWS exchange profile. New `gs://` and `azblob://` adapters require exact destination allowlists and matching Google Cloud or Azure exchange profiles. Existing HTTPS push and runtime AWS credential-chain behavior remain compatible. Kubernetes deployments can project multiple audience-specific service-account tokens to API and worker replicas.

## Ownership escalation and trends

Data owners can attach a versioned escalation policy to manual or scheduled ownership campaigns. Each policy has one to twenty unique reminder or overdue stages relative to campaign due time, a recipient class, and optional explicit integration destinations.

Stage events have durable claim, retry, error, delivery-count, and idempotency state. Repeated scheduler passes cannot create duplicate endpoint deliveries. Auditors can inspect escalation events and bounded daily trends for campaign completion, assignment response, remediation resolution, active overdue campaigns, and nonresponses.

## Performance baselines

`python -m app.benchmark_baselines` captures benchmark results with a documented non-secret topology and optional structural fingerprints from read-only PostgreSQL plans. Comparisons enforce configurable latency and throughput regression budgets and can optionally fail on plan drift.

Reference topology documents cover local, small PostgreSQL, and large PostgreSQL qualification. Baselines support controlled comparison; they do not certify production capacity.

## Upgrade

1. Stop API and worker processes.
2. Create and verify database, evidence, graph-export, and governance-package backups.
3. Review signing and verification profiles, connector plugin provenance and capability policy, workload exchange trust, destination allowlists, projected subject tokens, escalation routing, and regression budgets.
4. Run `alembic upgrade head`.
5. Start migration, API, and worker roles from the same v1.7 image and plugin set.
6. Verify `/health`, `/ready`, Alembic revision `20260731_0006`, and tenant isolation.
7. Generate and independently verify one signed synthetic governance package.
8. Inspect every connector manifest and exercise one policy denial.
9. Test each enabled exchange profile and export sink with an approved synthetic destination.
10. Launch one synthetic campaign with a due escalation stage and confirm idempotent delivery.
11. Capture and compare one representative performance baseline.

Downgrades are not supported. Restore the verified pre-upgrade database and object-storage state if rollback is required. Remote export sink objects require their own governed cleanup.

## Compatibility and limitations

- Existing APIs and v1.1 through v1.6 workflows remain available.
- Unsigned packages remain readable unless `ODG_GOVERNANCE_PACKAGE_SIGNING_REQUIRED=true`; they cannot become cryptographically trusted after creation without producing a new package.
- Sigstore signing and verification require a compatible external `cosign` executable. Bundles are verified offline against pinned certificate identity and issuer.
- Plugin packages execute in process and must be installed identically on API and worker images.
- Workload exchange profiles support AWS, Azure, and Google Cloud only. Each exchange is performed when credentials are requested; no application token cache is added in v1.7.
- Cloud export adapters are write-only. Destination retention, immutability, deletion, and independent integrity checks remain external responsibilities.
- Escalation recipients are routing metadata delivered through configured integration endpoints; OpenDataGraph does not send email directly.
- Trend windows are bounded summaries of OpenDataGraph campaign records, not proof of external entitlement review.
- Performance baselines are environment-specific comparative evidence, not certified throughput or capacity.

## License

OpenDataGraph v1.7.0 is source-available under `FSL-1.1-ALv2`. The license permits internal use, non-commercial education and research, and qualifying professional services while prohibiting competing commercial products and services. This release becomes available under Apache License 2.0 on July 31, 2028. Earlier releases retain the terms distributed with those releases.
