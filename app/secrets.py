import os
import re
from pathlib import Path

from app.config import settings


def resolve_secret(reference: str) -> str:
    if reference.startswith("env:"):
        name = reference.removeprefix("env:")
        if not re.fullmatch(r"[A-Z][A-Z0-9_]*", name):
            raise ValueError("Environment secret references must use uppercase variable names")
        value = os.getenv(name)
        if value is None:
            raise ValueError(f"Secret environment variable is not set: {name}")
        return value
    if reference.startswith("file:"):
        path = Path(reference.removeprefix("file:")).expanduser().resolve()
        if not any(path.is_relative_to(root) for root in settings.secret_file_roots):
            raise ValueError("Secret file is outside ODG_SECRET_FILE_ROOTS")
        if path.stat().st_size > 1024 * 1024:
            raise ValueError("Secret files must not exceed 1 MiB")
        return path.read_text(encoding="utf-8").strip()
    raise ValueError("Secret references must use env:NAME or file:/path")
