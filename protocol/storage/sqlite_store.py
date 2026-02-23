from __future__ import annotations

import json
import sqlite3
from typing import Any, Dict, List, Optional

from .base import PointerStoreBackend


class SQLitePointerStore(PointerStoreBackend):
    """SQLite implementation of the pointer store backend contract."""

    def __init__(self, db_path: str = "agent_state.db") -> None:
        self.db_path = db_path

    def initialize(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS state_store (
                    pointer_id TEXT PRIMARY KEY,
                    raw_data TEXT,
                    summary TEXT,
                    metadata TEXT,
                    created_at_utc TEXT,
                    ttl_seconds INTEGER,
                    expires_at_utc TEXT
                )
                """
            )
            self._ensure_lifecycle_columns(conn)
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_state_store_expires_at_utc ON state_store(expires_at_utc)"
            )

    def _ensure_lifecycle_columns(self, conn: sqlite3.Connection) -> None:
        existing_columns = {
            row[1] for row in conn.execute("PRAGMA table_info(state_store)").fetchall()
        }

        if "created_at_utc" not in existing_columns:
            conn.execute("ALTER TABLE state_store ADD COLUMN created_at_utc TEXT")
        if "ttl_seconds" not in existing_columns:
            conn.execute("ALTER TABLE state_store ADD COLUMN ttl_seconds INTEGER")
        if "expires_at_utc" not in existing_columns:
            conn.execute("ALTER TABLE state_store ADD COLUMN expires_at_utc TEXT")

        conn.execute(
            "UPDATE state_store SET created_at_utc = ? WHERE created_at_utc IS NULL",
            (self.parse_now_utc().isoformat(),),
        )

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
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO state_store
                (pointer_id, raw_data, summary, metadata, created_at_utc, ttl_seconds, expires_at_utc)
                VALUES (?, ?, ?, ?, ?, ?, ?)
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
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("SELECT raw_data FROM state_store WHERE pointer_id = ?", (pointer_id,))
            row = cursor.fetchone()
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

        now_iso = self.parse_now_utc(now_utc).isoformat()
        query = """
            SELECT pointer_id, summary, metadata, created_at_utc, ttl_seconds, expires_at_utc
            FROM state_store
        """
        params: List[Any] = []
        if not include_expired:
            query += " WHERE expires_at_utc IS NULL OR expires_at_utc > ?"
            params.append(now_iso)
        query += " ORDER BY created_at_utc DESC, pointer_id DESC"
        if limit is not None:
            query += " LIMIT ?"
            params.append(limit)

        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(query, tuple(params)).fetchall()

        pointers: List[Dict[str, Any]] = []
        for row in rows:
            expires_at = row[5]
            metadata = json.loads(row[2]) if row[2] else {}
            pointers.append(
                {
                    "pointer_id": row[0],
                    "summary": row[1],
                    "metadata": metadata,
                    "created_at_utc": row[3],
                    "ttl_seconds": row[4],
                    "expires_at_utc": expires_at,
                    "is_expired": self.is_expired(expires_at, now_utc=now_utc),
                }
            )
        return pointers

    def delete_pointer(self, pointer_id: str) -> bool:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("DELETE FROM state_store WHERE pointer_id = ?", (pointer_id,))
            return cursor.rowcount > 0
