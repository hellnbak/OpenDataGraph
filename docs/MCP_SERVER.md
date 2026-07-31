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

v1.8 makes read-oriented catalog, summary, AI activity, and relationship tools policy-enforcement points. With the default `ODG_MCP_AUTHORIZATION_REQUIRED=true`, each tool requests an AuthZEN runtime decision before reading its underlying API. A denial raises a tool error and still has a durable receipt. Conditional decisions include obligations; the MCP host remains responsible for rejecting obligations it cannot apply.

`authorize_ai_data_use` remains compatible with the original asset-specific policy API. `authorize_runtime_access` exposes the generic AuthZEN path, while `list_runtime_decision_receipts` exposes tenant-scoped audit evidence to an authorized caller.

The server uses the SDK's default local transport. It does not provide a public remote MCP OAuth server, delete source data, change provider permissions, upload evidence, approve dispositions, replay integrations, manage service-account or workload credentials, connector capability policy, plugins, signing trust, escalation policy, or cloud exchange, schedule campaigns, create packages or exports, or expose connector or integration secret references.
