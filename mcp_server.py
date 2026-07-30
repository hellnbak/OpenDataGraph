"""OpenDataGraph MCP server. Run: python mcp_server.py"""
import os
import httpx
from mcp.server.fastmcp import FastMCP

BASE=os.getenv("ODG_API_URL","http://localhost:8080")
mcp=FastMCP("OpenDataGraph")

def call(method,path,**kwargs):
    with httpx.Client(base_url=BASE,timeout=30) as client:
        r=client.request(method,path,**kwargs); r.raise_for_status(); return r.json()

@mcp.tool()
def search_data_assets(search:str="", sensitivity:str="", source:str="") -> list[dict]:
    """Search cataloged enterprise data assets and their classifications."""
    params={k:v for k,v in {"search":search,"sensitivity":sensitivity,"source":source}.items() if v}
    return call("GET","/api/v1/assets",params=params)[:100]

@mcp.tool()
def get_data_asset(asset_id:int) -> dict:
    """Get lifecycle, classification, ownership, and AI policy context for one asset."""
    return call("GET",f"/api/v1/assets/{asset_id}")

@mcp.tool()
def list_ai_agents() -> list[dict]:
    """List registered AI agents, owners, purposes, approved data, and destinations."""
    return call("GET","/api/v1/agents")

@mcp.tool()
def authorize_ai_data_use(asset_id:int, agent_key:str, destination:str, purpose:str, action:str="send") -> dict:
    """Evaluate whether an AI agent may use a data asset and return required controls."""
    return call("POST","/api/v1/policy/evaluate",json={"asset_id":asset_id,"agent_key":agent_key,"destination":destination,"purpose":purpose,"action":action})

@mcp.tool()
def data_intelligence_summary() -> dict:
    """Get enterprise-wide sensitive data, lifecycle, source, and AI readiness metrics."""
    return call("GET","/api/v1/summary")

if __name__ == "__main__": mcp.run()
