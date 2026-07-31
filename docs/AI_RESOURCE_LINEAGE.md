# AI Resource Lineage

OpenDataGraph v1.8 treats runtime AI components as governed resources and distinguishes declared relationships from observed behavior.

## Resource registry

Supported resource types are:

- `model`
- `prompt`
- `vector-index`
- `tool`
- `endpoint`
- `ai-system`

Each tenant-scoped resource has a stable key, name, owner, provider, region, status, risk tier, and bounded metadata. Status is `draft`, `review`, `approved`, or `disabled`; risk tier is `low`, `medium`, `high`, or `critical`. Runtime authorization denies missing and non-approved AI resources.

Endpoints:

- `POST|GET /api/v1/ai/resources`
- `GET|PATCH /api/v1/ai/resources/{resource_key}`

Creation and update require `data-owner`; reads require `read-only`.

Metadata is limited to 32 KiB. Credentials, authorization values, tokens, secrets, prompts, and responses are rejected by key. Metadata is operational context, not a content store.

## Expected relationships

Data owners declare relationships through:

```text
POST /api/v1/ai/lineage/relationships
```

References can target registered AI resources, registered agents, registered data assets, or external dataset identifiers. Relationship names are stable lowercase identifiers such as:

- `retrieves_from`
- `calls`
- `uses_prompt`
- `served_by`
- `trained_on`
- `approved_for`

Declarations are idempotent by tenant, source, relationship, and target. Updating a declaration changes expected state and bounded metadata without producing duplicate graph edges.

## Runtime observations and drift

Analysts send observations through:

```text
POST /api/v1/ai/lineage/observations
```

`event_id` is tenant-scoped and idempotent. Reusing it for a different relationship is rejected. An observation updates first-seen, last-seen, and count fields on the relationship.

Drift is `true` when the observed relationship is missing from the expected active topology or the existing relationship is inactive. Drift is `false` when the relationship is both active and expected. Drift is a governance signal for investigation, not proof of compromise.

Auditors list drift through:

```text
GET /api/v1/ai/lineage/drift
```

All relationships project into the existing `graph_edges` store with relationship identity, expected state, status, observation count, and first and last observation timestamps. Existing graph query, path explanation, and export bounds still apply.

## Evidence and isolation

Governance analytics count drift events in the selected window. Governance evidence packages can include the `ai-lineage` category. The package contains identifiers, relationship, drift state, and timestamps, not observation metadata or customer content.

Resources, declarations, observations, graph projections, idempotency, and list operations are tenant-scoped. Strict isolation requirements should continue to use separate databases.

See [Runtime authorization](RUNTIME_AUTHORIZATION.md), [Knowledge graph](KNOWLEDGE_GRAPH.md), and [Governance evidence packages](GOVERNANCE_EVIDENCE_PACKAGES.md).
