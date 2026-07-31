import base64
import json
from collections.abc import Callable
from urllib.parse import quote

from sqlalchemy import bindparam, create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.pool import NullPool

from .sdk import AssetRecord, ScanBatch


class PostgreSQLConnector:
    source = "postgresql"

    def __init__(
        self,
        account: str,
        dsn: str,
        schemas: list[str] | None = None,
        before_request: Callable[[], None] | None = None,
    ):
        if not isinstance(account, str) or not account.strip() or len(account) > 160:
            raise ValueError("PostgreSQL connector account is invalid")
        parsed = make_url(dsn)
        if parsed.drivername not in {"postgresql", "postgresql+psycopg"}:
            raise ValueError("PostgreSQL connector secret must contain a PostgreSQL DSN")
        if not parsed.host or not parsed.database:
            raise ValueError("PostgreSQL connector DSN requires a host and database")
        normalized_schemas = sorted(set(schemas or []))
        if len(normalized_schemas) > 100 or any(
            not isinstance(schema, str)
            or not schema.strip()
            or len(schema) > 63
            for schema in normalized_schemas
        ):
            raise ValueError("PostgreSQL connector schemas are invalid")
        self.account = account.strip()
        self.dsn = dsn
        self.schemas = normalized_schemas
        self.before_request = before_request

    def scan(self, cursor: str | None = None, max_items: int = 500) -> ScanBatch:
        if not 1 <= max_items <= 5000:
            raise ValueError("PostgreSQL connector max_items must be 1 to 5000")
        cursor_schema, cursor_table = _decode_cursor(cursor)
        if self.before_request:
            self.before_request()
        engine = create_engine(self.dsn, poolclass=NullPool, pool_pre_ping=True)
        try:
            with engine.connect() as connection:
                rows = list(
                    connection.execute(
                        _catalog_statement(),
                        {
                            "cursor_schema": cursor_schema,
                            "cursor_table": cursor_table,
                            "filter_schemas": bool(self.schemas),
                            "schemas": self.schemas or [""],
                            "limit": max_items + 1,
                        },
                    ).mappings()
                )
        finally:
            engine.dispose()
        complete = len(rows) <= max_items
        selected = rows[:max_items]
        records = [self._record(row) for row in selected]
        next_cursor = None
        if not complete and selected:
            last = selected[-1]
            next_cursor = _encode_cursor(last["table_schema"], last["table_name"])
        return ScanBatch(records=records, next_cursor=next_cursor, complete=complete)

    def _record(self, row) -> AssetRecord:
        schema = row["table_schema"]
        table = row["table_name"]
        account = quote(self.account, safe="")
        schema_path = quote(schema, safe="")
        table_path = quote(table, safe="")
        return AssetRecord(
            source=self.source,
            source_account=self.account,
            external_id=f"postgresql://{account}/{schema_path}/{table_path}",
            name=table,
            path=f"postgresql://{account}/{schema_path}/{table_path}",
            mime_type="application/vnd.postgresql.table",
            owner=row.get("owner") or "unknown",
            public_access=False,
            encryption="Not evaluated",
            metadata={
                "schema": schema,
                "table_type": row["table_type"],
                "estimated_rows": int(row.get("estimated_rows") or 0),
                "column_count": int(row.get("column_count") or 0),
                "content_retrieved": False,
                "public_access_evidence": "not-evaluated",
                "transport_encryption_evidence": "not-evaluated",
                "timestamp_provenance": "catalog-scan-time",
            },
        )


def _catalog_statement():
    return text(
        """
        SELECT
            t.table_schema,
            t.table_name,
            t.table_type,
            COALESCE(c.reltuples::bigint, 0) AS estimated_rows,
            COALESCE(pg_get_userbyid(c.relowner), 'unknown') AS owner,
            (
                SELECT count(*)
                FROM information_schema.columns AS col
                WHERE col.table_schema = t.table_schema
                  AND col.table_name = t.table_name
            ) AS column_count
        FROM information_schema.tables AS t
        LEFT JOIN pg_catalog.pg_namespace AS n
          ON n.nspname = t.table_schema
        LEFT JOIN pg_catalog.pg_class AS c
          ON c.relnamespace = n.oid
         AND c.relname = t.table_name
        WHERE t.table_schema NOT IN ('pg_catalog', 'information_schema')
          AND (
              :cursor_schema = ''
              OR t.table_schema > :cursor_schema
              OR (t.table_schema = :cursor_schema AND t.table_name > :cursor_table)
          )
          AND (NOT :filter_schemas OR t.table_schema IN :schemas)
        ORDER BY t.table_schema, t.table_name
        LIMIT :limit
        """
    ).bindparams(bindparam("schemas", expanding=True))


def _encode_cursor(schema: str, table: str) -> str:
    payload = json.dumps([schema, table], separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(payload).decode().rstrip("=")


def _decode_cursor(cursor: str | None) -> tuple[str, str]:
    if cursor is None:
        return "", ""
    if not isinstance(cursor, str) or not cursor or len(cursor) > 2048:
        raise ValueError("PostgreSQL connector cursor is invalid")
    try:
        padding = "=" * (-len(cursor) % 4)
        value = json.loads(base64.urlsafe_b64decode(cursor + padding))
    except (ValueError, json.JSONDecodeError) as exc:
        raise ValueError("PostgreSQL connector cursor is invalid") from exc
    if (
        not isinstance(value, list)
        or len(value) != 2
        or any(not isinstance(item, str) or len(item) > 63 for item in value)
    ):
        raise ValueError("PostgreSQL connector cursor is invalid")
    return value[0], value[1]
