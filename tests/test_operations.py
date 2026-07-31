import sqlite3

from app.config import settings
from app.operations import backup


def test_sqlite_backup_includes_manifest_and_database(tmp_path, monkeypatch):
    source = tmp_path / "source.db"
    with sqlite3.connect(source) as connection:
        connection.execute("create table example (id integer primary key)")
        connection.execute("insert into example values (1)")
    monkeypatch.setattr(settings, "database_url", f"sqlite:///{source}")
    monkeypatch.setattr(settings, "evidence_backend", "local")
    monkeypatch.setattr(settings, "evidence_local_directory", tmp_path / "evidence")
    destination = backup(tmp_path / "backup")
    assert (destination / "manifest.json").exists()
    with sqlite3.connect(destination / "database.sqlite3") as connection:
        assert connection.execute("select count(*) from example").fetchone()[0] == 1
