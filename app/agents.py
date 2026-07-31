from datetime import UTC, datetime, timedelta


NOW = datetime.now(UTC).replace(tzinfo=None)
DEMO_AGENTS=[
 dict(key="customer-support-copilot",name="Customer Support Copilot",owner="Customer Operations",business_purpose="Summarize support cases and draft responses",framework="MCP + custom RAG",models="Claude Enterprise, internal-rag",allowed_domains="Customer Support,Customer Data",max_sensitivity="Confidential",allowed_destinations="internal-rag,claude-enterprise,private-model",approval_status="Approved",risk_level="Medium",last_activity_at=NOW-timedelta(minutes=5)),
 dict(key="engineering-coding-agent",name="Engineering Coding Agent",owner="Platform Engineering",business_purpose="Explain code and generate tests",framework="MCP",models="Private Qwen, GitHub Copilot",allowed_domains="Engineering,Product",max_sensitivity="Confidential",allowed_destinations="private-model,github-copilot-enterprise",approval_status="Approved",risk_level="Medium",last_activity_at=NOW-timedelta(minutes=18)),
 dict(key="finance-forecast-agent",name="Finance Forecast Agent",owner="Finance",business_purpose="Analyze forecasts and prepare variance summaries",framework="LangGraph",models="Private Llama",allowed_domains="Finance",max_sensitivity="Restricted",allowed_destinations="private-model,bedrock-private",approval_status="Approved",risk_level="High",last_activity_at=NOW-timedelta(hours=2)),
 dict(key="unapproved-lab-agent",name="Unapproved Lab Agent",owner="Innovation Lab",business_purpose="Prototype general AI workflows",framework="Custom",models="External AI",allowed_domains="",max_sensitivity="Public",allowed_destinations="",approval_status="Review",risk_level="Critical",last_activity_at=NOW-timedelta(days=2)),
]
