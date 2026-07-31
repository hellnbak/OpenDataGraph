"""OpenDataGraph MCP server. Run: python mcp_server.py"""

import os
from uuid import uuid4

import httpx
from mcp.server.fastmcp import FastMCP

BASE = os.getenv("ODG_API_URL", "http://localhost:8080")
API_KEY = os.getenv("ODG_API_KEY", "")
MCP_AGENT_KEY = os.getenv("ODG_MCP_AGENT_KEY", "customer-support-copilot")
MCP_AUTHORIZATION_REQUIRED = os.getenv(
    "ODG_MCP_AUTHORIZATION_REQUIRED",
    "true",
).lower() in {"1", "true", "yes", "on"}
mcp = FastMCP("OpenDataGraph")
client = httpx.Client(
    base_url=BASE,
    timeout=30,
    headers={"X-API-Key": API_KEY} if API_KEY else {},
)


def call(method, path, **kwargs):
    response = client.request(method, path, **kwargs)
    response.raise_for_status()
    return response.json()


def governed_call(method, path, tool_name, resource_type, resource_id, **kwargs):
    if MCP_AUTHORIZATION_REQUIRED:
        authorization = runtime_authorization(
            resource_type,
            resource_id,
            "mcp.invoke",
            {
                "tool": tool_name,
                "destination": "internal-rag",
                "purpose": "mcp-context-access",
                "protocol": "mcp",
            },
        )
        if not authorization["decision"]:
            reason = authorization.get("context", {}).get(
                "reason",
                "OpenDataGraph runtime policy denied the MCP operation",
            )
            raise PermissionError(reason)
    return call(method, path, **kwargs)


def runtime_authorization(resource_type, resource_id, action, context=None):
    return call(
        "POST",
        "/access/v1/evaluation",
        headers={"X-Request-ID": str(uuid4())},
        json={
            "subject": {"type": "ai_agent", "id": MCP_AGENT_KEY},
            "resource": {"type": resource_type, "id": str(resource_id)},
            "action": {"name": action},
            "context": context or {},
        },
    )


@mcp.tool()
def search_data_assets(search: str = "", sensitivity: str = "", source: str = "") -> list[dict]:
    """Search cataloged enterprise data assets and their classifications."""
    params = {key: value for key, value in {"search": search, "sensitivity": sensitivity, "source": source}.items() if value}
    return governed_call(
        "GET",
        "/api/v1/assets",
        "search_data_assets",
        "catalog",
        "data-assets",
        params=params,
    )[:100]


@mcp.tool()
def get_data_asset(asset_id: int) -> dict:
    """Get lifecycle, classification, ownership, and AI policy context for one asset."""
    return governed_call(
        "GET",
        f"/api/v1/assets/{asset_id}",
        "get_data_asset",
        "data_asset",
        str(asset_id),
    )


@mcp.tool()
def list_ai_agents() -> list[dict]:
    """List registered AI agents, owners, purposes, approved data, and destinations."""
    return governed_call(
        "GET",
        "/api/v1/agents",
        "list_ai_agents",
        "catalog",
        "ai-agents",
    )


@mcp.tool()
def authorize_ai_data_use(asset_id: int, agent_key: str, destination: str, purpose: str, action: str = "send") -> dict:
    """Evaluate whether an AI agent may use a data asset and return required controls."""
    return call(
        "POST",
        "/api/v1/policy/evaluate",
        json={
            "asset_id": asset_id,
            "agent_key": agent_key,
            "destination": destination,
            "purpose": purpose,
            "action": action,
        },
    )


@mcp.tool()
def data_intelligence_summary() -> dict:
    """Get enterprise-wide sensitive data, lifecycle, source, and AI readiness metrics."""
    return governed_call(
        "GET",
        "/api/v1/summary",
        "data_intelligence_summary",
        "catalog",
        "summary",
    )


@mcp.tool()
def list_ai_usage_events(limit: int = 100) -> list[dict]:
    """List observed AI data-use events and their correlated policy decisions."""
    return governed_call(
        "GET",
        "/api/v1/ai-usage/events",
        "list_ai_usage_events",
        "catalog",
        "ai-usage-events",
        params={"limit": min(max(limit, 1), 1000)},
    )


@mcp.tool()
def get_data_relationships(asset_id: int | None = None, agent_key: str = "") -> list[dict]:
    """Get knowledge-graph relationships for a data asset or AI agent."""
    params = {}
    if asset_id is not None:
        params["asset_id"] = asset_id
    if agent_key:
        params["agent_key"] = agent_key
    resource_id = str(asset_id) if asset_id is not None else agent_key or "relationships"
    return governed_call(
        "GET",
        "/api/v1/graph/relationships",
        "get_data_relationships",
        "catalog",
        resource_id,
        params=params,
    )


@mcp.tool()
def authorize_runtime_access(
    resource_type: str,
    resource_id: str,
    action: str,
    purpose: str = "mcp-runtime-access",
    destination: str = "internal-rag",
) -> dict:
    """Request an AuthZEN-compatible runtime decision with obligations and a receipt."""
    return runtime_authorization(
        resource_type,
        resource_id,
        action,
        {"purpose": purpose, "destination": destination, "protocol": "mcp"},
    )


@mcp.tool()
def list_runtime_decision_receipts(limit: int = 100) -> list[dict]:
    """List recent runtime authorization receipts for the authenticated tenant."""
    return call(
        "GET",
        "/api/v1/runtime/decision-receipts",
        params={"limit": min(max(limit, 1), 1000)},
    )


if __name__ == "__main__":
    mcp.run()
