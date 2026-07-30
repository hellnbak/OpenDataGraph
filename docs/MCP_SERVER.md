# MCP Server

The MCP server exposes OpenDataGraph context to compatible AI hosts while keeping policy decisions centralized.

## Tools

- `search_data_assets`
- `get_data_asset`
- `list_ai_agents`
- `authorize_ai_data_use`
- `data_intelligence_summary`
- `list_ai_usage_events`
- `get_data_relationships`

## Run

Start OpenDataGraph, then:

```bash
ODG_API_URL=http://localhost:8080 ODG_API_KEY=development-key python mcp_server.py
```

`ODG_API_KEY` is optional only when application authentication is disabled. The server does not delete source data or change provider permissions.
