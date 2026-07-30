from datetime import datetime

from .sdk import AssetRecord, ScanBatch


class GitHubConnector:
    source = "github"

    def __init__(self, organization: str, token: str, api_url: str = "https://api.github.com"):
        self.account = organization
        self.token = token
        self.api_url = api_url.rstrip("/")

    def scan(self, cursor: str | None = None, max_items: int = 500) -> ScanBatch:
        import httpx

        page = int(cursor or "1")
        headers = {"Authorization": f"Bearer {self.token}", "Accept": "application/vnd.github+json"}
        response = httpx.get(
            f"{self.api_url}/orgs/{self.account}/repos",
            headers=headers,
            params={"page": page, "per_page": min(100, max_items), "sort": "updated"},
            timeout=30,
        )
        response.raise_for_status()
        repositories = response.json()
        records = [
            AssetRecord(
                source=self.source,
                source_account=self.account,
                external_id=f"github://{repository['full_name']}",
                name=repository["name"],
                path=repository["html_url"],
                mime_type="application/vnd.github.repository",
                owner=self.account,
                created_at=_dt(repository.get("created_at")),
                modified_at=_dt(repository.get("updated_at")),
                public_access=not repository.get("private", True),
                encryption="Provider-managed",
                metadata={
                    "default_branch": repository.get("default_branch"),
                    "language": repository.get("language"),
                    "archived": repository.get("archived", False),
                    "visibility": repository.get("visibility"),
                },
            )
            for repository in repositories[:max_items]
        ]
        complete = len(repositories) < min(100, max_items)
        return ScanBatch(records=records, next_cursor=None if complete else str(page + 1), complete=complete)


def _dt(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).replace(tzinfo=None) if value else None
