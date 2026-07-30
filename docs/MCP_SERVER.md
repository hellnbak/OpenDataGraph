# OpenDataGraph MCP Server

The MCP server exposes the data intelligence and policy layers to compatible AI hosts while keeping policy decisions centralized in OpenDataGraph.

## Tools

- `search_data_assets`
- `get_data_asset`
- `list_ai_agents`
- `authorize_ai_data_use`
- `data_intelligence_summary`

## Run

Start OpenDataGraph, then:

```bash
ODG_API_URL=http://localhost:8080 python mcp_server.py
```

Example stdio client configuration:

```json
{
  "mcpServers": {
    "opendatagraph": {
      "command": "python",
      "args": ["/absolute/path/to/OpenDataGraph/mcp_server.py"],
      "env": {"ODG_API_URL": "http://localhost:8080"}
    }
  }
}
```

The MCP server has read-only catalog tools plus one authorization tool. It does not delete data or change source-system permissions.
