import argparse
import json
import os
import shutil
import sqlite3
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy.engine import make_url

from .config import settings


def backup(output: Path, force: bool = False) -> Path:
    output = output.resolve()
    if output.exists() and any(output.iterdir()) and not force:
        raise FileExistsError("Backup directory is not empty; pass --force to replace its contents")
    output.mkdir(parents=True, exist_ok=True)
    url = make_url(settings.database_url)
    database_file = _backup_database(url, output)
    evidence = _backup_evidence(output)
    manifest = {
        "format_version": 1,
        "created_at": datetime.now(UTC).isoformat(),
        "application_version": settings.version,
        "database_backend": url.get_backend_name(),
        "database_file": database_file.name,
        "evidence": evidence,
    }
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return output


def restore(source: Path, force: bool = False) -> None:
    if not force:
        raise ValueError("Restore is destructive; pass --force after stopping application and worker processes")
    source = source.resolve()
    manifest = json.loads((source / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("format_version") != 1:
        raise ValueError("Unsupported backup format")
    url = make_url(settings.database_url)
    backend = url.get_backend_name()
    if backend != manifest.get("database_backend"):
        raise ValueError("Backup database backend does not match ODG_DATABASE_URL")
    database_file = source / manifest["database_file"]
    _restore_database(url, database_file)
    if manifest.get("evidence") == "local":
        destination = settings.evidence_local_directory.resolve()
        if destination.exists():
            shutil.rmtree(destination)
        shutil.copytree(source / "evidence", destination)


def _backup_database(url, output: Path) -> Path:
    backend = url.get_backend_name()
    if backend == "sqlite":
        source_path = Path(url.database or "").resolve()
        destination = output / "database.sqlite3"
        with sqlite3.connect(source_path) as source, sqlite3.connect(destination) as target:
            source.backup(target)
        return destination
    if backend == "postgresql":
        destination = output / "database.dump"
        env = _postgres_environment(url)
        command = [
            "pg_dump",
            "--format=custom",
            "--no-owner",
            "--file",
            str(destination),
            *_postgres_connection_args(url),
        ]
        subprocess.run(command, env=env, check=True)
        return destination
    raise ValueError(f"Unsupported database backend: {backend}")


def _restore_database(url, database_file: Path) -> None:
    backend = url.get_backend_name()
    if backend == "sqlite":
        destination = Path(url.database or "").resolve()
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_suffix(".restore")
        shutil.copy2(database_file, temporary)
        temporary.replace(destination)
        return
    if backend == "postgresql":
        command = [
            "pg_restore",
            "--clean",
            "--if-exists",
            "--no-owner",
            "--dbname",
            url.database or "",
            *_postgres_connection_args(url, include_database=False),
            str(database_file),
        ]
        subprocess.run(command, env=_postgres_environment(url), check=True)
        return
    raise ValueError(f"Unsupported database backend: {backend}")


def _backup_evidence(output: Path) -> str:
    if settings.evidence_backend != "local":
        return "external"
    source = settings.evidence_local_directory.resolve()
    destination = output / "evidence"
    if source.exists():
        shutil.copytree(source, destination, dirs_exist_ok=True)
    else:
        destination.mkdir()
    return "local"


def _postgres_connection_args(url, include_database: bool = True) -> list[str]:
    arguments = []
    if url.host:
        arguments += ["--host", url.host]
    if url.port:
        arguments += ["--port", str(url.port)]
    if url.username:
        arguments += ["--username", url.username]
    if include_database and url.database:
        arguments += ["--dbname", url.database]
    return arguments


def _postgres_environment(url) -> dict:
    environment = os.environ.copy()
    if url.password:
        environment["PGPASSWORD"] = url.password
    return environment


def main() -> None:
    parser = argparse.ArgumentParser(description="OpenDataGraph backup and restore operations")
    subparsers = parser.add_subparsers(dest="operation", required=True)
    backup_parser = subparsers.add_parser("backup")
    backup_parser.add_argument("--output", type=Path, required=True)
    backup_parser.add_argument("--force", action="store_true")
    restore_parser = subparsers.add_parser("restore")
    restore_parser.add_argument("--source", type=Path, required=True)
    restore_parser.add_argument("--force", action="store_true")
    arguments = parser.parse_args()
    if arguments.operation == "backup":
        location = backup(arguments.output, force=arguments.force)
        print(location)
    else:
        restore(arguments.source, force=arguments.force)


if __name__ == "__main__":
    main()
