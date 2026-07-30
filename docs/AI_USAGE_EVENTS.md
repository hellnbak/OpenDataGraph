# AI Usage Events

AI gateways, agents, MCP clients, and internal applications can record actual data use through `POST /api/v1/ai-usage/events`.

An event includes:

- stable event ID
- AI agent key
- user or workload identity
- data asset ID
- model and destination
- purpose and action
- event timestamp
- optional metadata

## Idempotency

The stable event ID is unique. Repeating an accepted event returns the existing decision without creating another event.

## Policy correlation

Ingestion evaluates the current policy bundle and records the resulting decision and risk score. It also records an `agent -> accessed -> asset` graph edge containing the event ID, model, and decision.

## Privacy

Use stable internal identifiers instead of unnecessary personal details. Do not include prompts, response bodies, credentials, or raw file content in event metadata.
