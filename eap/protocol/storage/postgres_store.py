from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .base import PointerStoreBackend


class _PostgresPointerClient:
    def initialize(self) -> None:
        raise NotImplementedError

    def insert_pointer(
        self,
        pointer_id: str,
        raw_data: str,
        summary: str,
        metadata: Dict[str, Any],
        created_at_utc: str,
        ttl_seconds: Optional[int],
        expires_at_utc: Optional[str],
    ) -> None:
        raise NotImplementedError

    def retrieve_pointer(self, pointer_id: str) -> Any:
        raise NotImplementedError

    def list_pointers(
        self,
        include_expired: bool = True,
        now_utc: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        raise NotImplementedError

    def delete_pointer(self, pointer_id: str) -> bool:
        raise NotImplementedError


class PsycopgPointerClient(_PostgresPointerClient):
    IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

    def __init__(
        self,
        dsn: str,
        schema: str = "public",
        table_name: str = "eap_state_store",
    ) -> None:
        self.dsn = dsn
        self.schema = self._validate_identifier(schema, "schema")
        self.table_name = self._validate_identifier(table_name, "table_name")
        self.qualified_table = f'"{self.schema}"."{self.table_name}"'
        self._psycopg = self._import_psycopg()

    @classmethod
    def _validate_identifier(cls, value: str, field_name: str) -> str:
        if not cls.IDENTIFIER_RE.match(value):
            raise ValueError(f"Invalid PostgreSQL {field_name}: {value!r}")
        return value

    @staticmethod
    def _import_psycopg():
        try:
            import psycopg  # type: ignore
        except ImportError as exc:  # pragma: no cover - depends on runtime env
            raise RuntimeError(
                "PostgresPointerStore requires the 'psycopg' package. "
                "Install with: pip install psycopg[binary]"
            ) from exc
        return psycopg

    def _connect(self):
        return self._psycopg.connect(self.dsn)

    @staticmethod
    def _normalize_iso(value: Any) -> Optional[str]:
        if value is None:
            return None
        if isinstance(value, datetime):
            dt = value
        else:
            dt = datetime.fromisoformat(str(value))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).isoformat()

    def initialize(self) -> None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(f'CREATE SCHEMA IF NOT EXISTS "{self.schema}"')
                cur.execute(
                    f"""
                    CREATE TABLE IF NOT EXISTS {self.qualified_table} (
                        pointer_id TEXT PRIMARY KEY,
                        raw_data TEXT,
                        summary TEXT,
                        metadata JSONB,
                        created_at_utc TIMESTAMPTZ,
                        ttl_seconds INTEGER,
                        expires_at_utc TIMESTAMPTZ
                    )
                    """
                )
                cur.execute(
                    f"""
                    CREATE INDEX IF NOT EXISTS idx_{self.table_name}_expires_at_utc
                    ON {self.qualified_table}(expires_at_utc)
                    """
                )

    def insert_pointer(
        self,
        pointer_id: str,
        raw_data: str,
        summary: str,
        metadata: Dict[str, Any],
        created_at_utc: str,
        ttl_seconds: Optional[int],
        expires_at_utc: Optional[str],
    ) -> None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    INSERT INTO {self.qualified_table}
                    (pointer_id, raw_data, summary, metadata, created_at_utc, ttl_seconds, expires_at_utc)
                    VALUES (%s, %s, %s, %s::jsonb, %s::timestamptz, %s, %s::timestamptz)
                    """,
                    (
                        pointer_id,
                        raw_data,
                        summary,
                        json.dumps(metadata),
                        created_at_utc,
                        ttl_seconds,
                        expires_at_utc,
                    ),
                )

    def retrieve_pointer(self, pointer_id: str) -> Any:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"SELECT raw_data FROM {self.qualified_table} WHERE pointer_id = %s",
                    (pointer_id,),
                )
                row = cur.fetchone()

        if not row:
            raise KeyError(f"Pointer {pointer_id} not found in persistent storage.")
        return row[0]

    def list_pointers(
        self,
        include_expired: bool = True,
        now_utc: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        if limit is not None and limit <= 0:
            raise ValueError("limit must be > 0 when provided.")

        now_iso = PointerStoreBackend.parse_now_utc(now_utc).isoformat()
        query = f"""
            SELECT pointer_id, summary, metadata, created_at_utc, ttl_seconds, expires_at_utc
            FROM {self.qualified_table}
        """
        params: List[Any] = []
        if not include_expired:
            query += " WHERE expires_at_utc IS NULL OR expires_at_utc > %s::timestamptz"
            params.append(now_iso)
        query += " ORDER BY created_at_utc DESC, pointer_id DESC"
        if limit is not None:
            query += " LIMIT %s"
            params.append(limit)

        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(query, tuple(params))
                rows = cur.fetchall()

        pointers: List[Dict[str, Any]] = []
        for row in rows:
            metadata_value = row[2]
            if isinstance(metadata_value, str):
                metadata = json.loads(metadata_value)
            elif metadata_value is None:
                metadata = {}
            else:
                metadata = dict(metadata_value)
            expires_at_utc = self._normalize_iso(row[5])
            pointers.append(
                {
                    "pointer_id": row[0],
                    "summary": row[1],
                    "metadata": metadata,
                    "created_at_utc": self._normalize_iso(row[3]),
                    "ttl_seconds": row[4],
                    "expires_at_utc": expires_at_utc,
                    "is_expired": PointerStoreBackend.is_expired(expires_at_utc, now_utc=now_utc),
                }
            )
        return pointers

    def delete_pointer(self, pointer_id: str) -> bool:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"DELETE FROM {self.qualified_table} WHERE pointer_id = %s",
                    (pointer_id,),
                )
                return cur.rowcount > 0


class PostgresPointerStore(PointerStoreBackend):
    """PostgreSQL implementation of the pointer store backend contract."""

    def __init__(
        self,
        dsn: str = "postgresql://localhost:5432/eap",
        schema: str = "public",
        table_name: str = "eap_state_store",
        client: Optional[_PostgresPointerClient] = None,
    ) -> None:
        self.client = client or PsycopgPointerClient(dsn=dsn, schema=schema, table_name=table_name)

    def initialize(self) -> None:
        self.client.initialize()

    def store_pointer(
        self,
        pointer_id: str,
        raw_data: str,
        summary: str,
        metadata: Dict[str, Any],
        created_at_utc: str,
        ttl_seconds: Optional[int],
        expires_at_utc: Optional[str],
    ) -> None:
        self.client.insert_pointer(
            pointer_id=pointer_id,
            raw_data=raw_data,
            summary=summary,
            metadata=metadata,
            created_at_utc=created_at_utc,
            ttl_seconds=ttl_seconds,
            expires_at_utc=expires_at_utc,
        )

    def retrieve_pointer(self, pointer_id: str) -> Any:
        return self.client.retrieve_pointer(pointer_id)

    def list_pointers(
        self,
        include_expired: bool = True,
        now_utc: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        return self.client.list_pointers(
            include_expired=include_expired,
            now_utc=now_utc,
            limit=limit,
        )

    def delete_pointer(self, pointer_id: str) -> bool:
        return self.client.delete_pointer(pointer_id)
