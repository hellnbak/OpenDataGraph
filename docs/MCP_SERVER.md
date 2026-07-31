# MCP Server

The MCP server exposes OpenDataGraph context to compatible AI hosts while keeping catalog and policy decisions centralized.

## Tools

- `search_data_assets`
- `get_data_asset`
- `list_ai_agents`
- `authorize_ai_data_use`
- `data_intelligence_summary`
- `list_ai_usage_events`
- `get_data_relationships`
- `authorize_runtime_access`
- `list_runtime_decision_receipts`

## Run

Start OpenDataGraph, then:

```bash
ODG_API_URL=http://localhost:8080 \
ODG_API_KEY=development-key \
ODG_MCP_AGENT_KEY=customer-support-copilot \
python mcp_server.py
```

`ODG_API_KEY` is optional only when application authentication is disabled. When enabled, the key determines both role and tenant; MCP tool calls cannot select another tenant. `ODG_MCP_AGENT_KEY` must identify a registered, approved AI agent in that tenant.

The local server makes read-oriented catalog, summary, AI activity, and relationship tools policy-enforcement points. With the default `ODG_MCP_AUTHORIZATION_REQUIRED=true`, each tool requests an AuthZEN runtime decision before reading its underlying API. A denial raises a tool error and still has a durable receipt. Conditional decisions include obligations; the MCP host remains responsible for rejecting obligations it cannot apply.

`authorize_ai_data_use` remains compatible with the original asset-specific policy API. `authorize_runtime_access` exposes the generic AuthZEN path, while `list_runtime_decision_receipts` exposes tenant-scoped audit evidence to an authorized caller.

## Stateless remote preview

v1.9 adds an opt-in `POST /mcp` gateway for the `2026-07-28` stateless protocol profile. Enable it with `ODG_REMOTE_MCP_ENABLED=true`, configure a registered approved agent in `ODG_REMOTE_MCP_DEFAULT_AGENT_KEY`, and send `MCP-Protocol-Version: 2026-07-28`. Authenticated deployments require an OIDC bearer token with at least `analyst`; API keys and service-account keys are intentionally rejected on this route.

The gateway supports `server/discover`, `tools/list`, and bounded `tools/call` for runtime authorization, asset metadata, and receipt inspection. It returns tool TTL and protocol headers, maintains no handshake or server session, and does not persist MCP request bodies. The preview does not claim the Enterprise-Managed Authorization extension, dynamic client registration, elicitation, sampling, resources, prompts, notifications, or full remote MCP conformance. Place it behind TLS, OIDC audience validation, request-size controls, rate limiting, and network policy.

Neither MCP surface deletes source data, changes provider permissions, uploads evidence, approves dispositions, replays integrations, manages credentials or connector policy, changes signing trust, schedules campaigns, creates packages or exports, or exposes secret references.
