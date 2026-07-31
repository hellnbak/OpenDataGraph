from collections.abc import Iterable
from urllib.parse import urlsplit


def validate_https_url(url: str, allowed_hosts: Iterable[str] | None = None) -> str:
    parsed = urlsplit(url)
    if parsed.scheme != "https" or not parsed.hostname:
        raise ValueError("Connector endpoints must use an absolute HTTPS URL")
    if parsed.username or parsed.password:
        raise ValueError("Connector endpoints must not contain user information")
    if allowed_hosts is not None:
        normalized_hosts = {host.lower().strip() for host in allowed_hosts if host.strip()}
        if parsed.hostname.lower() not in normalized_hosts:
            raise ValueError("Connector endpoint host is not in the configured provider allowlist")
    return url.rstrip("/")
