# Connector Conformance and Capability Policy

OpenDataGraph v1.7 adds versioned connector manifests, a central registry, deterministic conformance checks, and tenant-scoped capability policy enforcement.

## Manifest contract

Every registered connector declares:

- connector and SDK versions;
- least-privilege permissions;
- expected egress hosts;
- content-access level;
- pagination and incremental cursor support;
- opaque cursor behavior;
- rate-limit behavior;
- timestamp provenance;
- public-access interpretation;
- whether destructive actions exist.

The canonical manifest has a SHA-256 digest. Connector runs record connector version, manifest digest, and the tenant policy version used at execution.

## Registry and plugins

Built-in connectors register directly. External Python packages may expose an `opendatagraph.connectors` entry point that returns `ConnectorRegistration`. Discovery alone does not enable a plugin: its entry-point name must also appear in `ODG_CONNECTOR_PLUGIN_ALLOWLIST`.

Plugins execute inside API and worker processes. Treat them as trusted application code, review their dependencies and release provenance, pin their versions, and deploy the same plugin set to every API, migration, and worker image. The capability policy limits declared behavior but is not a process sandbox.

## Capability policy

The default policy permits metadata-only, non-destructive connectors with opaque cursors. Administrators can set a tenant policy through:

```text
GET|PUT /api/v1/connectors/capability-policy
```

Policy fields are:

- `allowed_connectors` and `denied_connectors`;
- `allowed_content_access`;
- `allowed_egress_hosts`;
- `deny_destructive_actions`;
- `require_incremental_cursor`;
- `require_opaque_cursor`;
- `max_declared_permissions`.

`ODG_CONNECTOR_CAPABILITY_POLICY_JSON` supplies the deployment baseline. A tenant policy is versioned in the database and overlays that baseline. Policy is enforced when a connector job is accepted and again when the worker constructs the connector.

Auditors can inspect manifests and policy decisions without secrets:

```text
GET /api/v1/connectors/capabilities
```

## Conformance checks

Validate every installed manifest:

```bash
python -m connectors.conformance
```

Validate one manifest:

```bash
python -m connectors.conformance --connector postgresql
```

The CLI checks declarations only and does not call providers. Connector packages should also call `run_connector_conformance` with a deterministic fake adapter to validate normalized records, bounded pages, metadata-only behavior, and opaque cursor state.

Conformance does not prove provider permissions, data residency, or source behavior. Validate those separately with a least-privileged synthetic account and no live customer content.
