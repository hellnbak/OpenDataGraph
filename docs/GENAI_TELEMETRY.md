# GenAI Telemetry

OpenDataGraph v1.9 accepts OpenTelemetry Protocol JSON traces at `POST /v1/traces` and `POST /api/v1/telemetry/genai/otlp`. The endpoint requires `analyst`; event inspection requires `auditor`.

## Metadata-only boundary

The ingestion path recognizes spans with `gen_ai.*` attributes and retains only normalized operational fields:

- trace and span IDs;
- operation, provider, model, and optional OpenDataGraph agent key;
- input and output token counts;
- duration and finish reasons;
- an SHA-256 digest of bounded metadata attributes;
- whether content attributes were discarded.

Prompt, completion, message, system-instruction, tool-argument, and tool-result attributes are discarded before persistence. The original OTLP payload and arbitrary attribute values are not stored. Do not use this endpoint for content capture or debugging payload retention.

## Discovery and lineage

An unseen provider/model pair creates a model resource with owner `unassigned`, status `review`, risk tier `high`, and `discovered_by=opentelemetry`. Review-state models are denied by runtime authorization until a data owner assigns ownership and explicitly approves them.

When `opendatagraph.agent.key`, `gen_ai.agent.id`, or `gen_ai.agent.name` resolves to a registered agent, ingestion records an `agent invokes model` observation and projects the relationship into the graph. Unknown agents do not create identities automatically.

## Idempotency and bounds

Events use tenant-scoped `traceId` plus `spanId` identity. Repeated spans are counted as duplicates and do not create additional records or observations. Requests are limited to 2 MiB and `ODG_GENAI_TELEMETRY_BATCH_MAX` spans, with a hard maximum of 5,000.

The endpoint accepts OTLP/HTTP JSON only. Protobuf, gRPC, logs, metrics, baggage, sampling control, and a general-purpose collector are outside this release. Use an OpenTelemetry Collector to filter, batch, retry, authenticate, and export JSON traces to OpenDataGraph.
