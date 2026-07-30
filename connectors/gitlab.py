from datetime import datetime

from .sdk import AssetRecord, ScanBatch


class GitLabConnector:
    source = "gitlab"

    def __init__(self, group: str, token: str, api_url: str = "https://gitlab.com/api/v4"):
        self.account = group
        self.token = token
        self.api_url = api_url.rstrip("/")

    def scan(self, cursor: str | None = None, max_items: int = 500) -> ScanBatch:
        import httpx

        page = int(cursor or "1")
        response = httpx.get(
            f"{self.api_url}/groups/{self.account}/projects",
            headers={"PRIVATE-TOKEN": self.token},
            params={"page": page, "per_page": min(100, max_items), "include_subgroups": "true"},
            timeout=30,
        )
        response.raise_for_status()
        projects = response.json()
        records = [
            AssetRecord(
                source=self.source,
                source_account=self.account,
                external_id=f"gitlab://{project['path_with_namespace']}",
                name=project["name"],
                path=project["web_url"],
                mime_type="application/vnd.gitlab.project",
                owner=project["namespace"]["full_path"],
                created_at=_dt(project.get("created_at")),
                modified_at=_dt(project.get("last_activity_at")),
                public_access=project.get("visibility") == "public",
                encryption="Provider-managed",
                metadata={
                    "default_branch": project.get("default_branch"),
                    "archived": project.get("archived", False),
                    "visibility": project.get("visibility"),
                },
            )
            for project in projects[:max_items]
        ]
        complete = len(projects) < min(100, max_items)
        return ScanBatch(records=records, next_cursor=None if complete else str(page + 1), complete=complete)


def _dt(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).replace(tzinfo=None) if value else None
