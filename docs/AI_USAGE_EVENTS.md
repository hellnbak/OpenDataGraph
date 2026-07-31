# AI Usage Events

AI gateways, agents, MCP clients, and internal applications record observed data use through `POST /api/v1/ai-usage/events`.

An event includes a stable event ID, AI agent key, user or workload identity, data asset ID, model, destination, purpose, action, timestamp, and optional metadata.

## Tenant-scoped idempotency

The stable event ID is unique within the authenticated tenant. Repeating an accepted event in that tenant returns the existing decision without creating another event. Asset and agent correlation cannot cross tenants.

## Policy correlation

Ingestion evaluates the current policy bundle and records decision and risk score. It also records a tenant-scoped `agent -> accessed -> asset` edge containing event ID, model, and decision.

## Privacy

Use stable internal identifiers instead of unnecessary personal details. Do not include prompts, responses, credentials, raw file content, evidence bytes, or authorization headers in event metadata, logs, or traces.
