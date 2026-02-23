from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from .base import PointerStoreBackend


class RedisPointerStore(PointerStoreBackend):
    """Redis implementation of the pointer store backend contract."""

    def __init__(
        self,
        redis_url: str = "redis://localhost:6379/0",
        key_prefix: str = "eap:pointer_store",
        client: Any = None,
    ) -> None:
        self.redis_url = redis_url
        self.key_prefix = key_prefix
        if client is not None:
            self.client = client
            return

        try:
            import redis  # type: ignore
        except ImportError as exc:  # pragma: no cover - exercised in environments without redis dep
            raise RuntimeError(
                "RedisPointerStore requires the 'redis' package. "
                "Install with: pip install redis"
            ) from exc

        self.client = redis.Redis.from_url(redis_url, decode_responses=True)

    @property
    def _pointer_ids_key(self) -> str:
        return f"{self.key_prefix}:ids"

    def _pointer_key(self, pointer_id: str) -> str:
        return f"{self.key_prefix}:{pointer_id}"

    def initialize(self) -> None:
        # Redis schema is key-based; no upfront migration required.
        return None

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
        self.client.hset(
            self._pointer_key(pointer_id),
            mapping={
                "pointer_id": pointer_id,
                "raw_data": raw_data,
                "summary": summary,
                "metadata": json.dumps(metadata),
                "created_at_utc": created_at_utc,
                "ttl_seconds": "" if ttl_seconds is None else str(ttl_seconds),
                "expires_at_utc": "" if expires_at_utc is None else expires_at_utc,
            },
        )
        self.client.sadd(self._pointer_ids_key, pointer_id)

    def retrieve_pointer(self, pointer_id: str) -> Any:
        raw_data = self.client.hget(self._pointer_key(pointer_id), "raw_data")
        if raw_data is None:
            raise KeyError(f"Pointer {pointer_id} not found in persistent storage.")
        return raw_data

    def list_pointers(
        self,
        include_expired: bool = True,
        now_utc: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        if limit is not None and limit <= 0:
            raise ValueError("limit must be > 0 when provided.")

        pointer_ids = list(self.client.smembers(self._pointer_ids_key))
        rows: List[Dict[str, Any]] = []
        for pointer_id in pointer_ids:
            record = self.client.hgetall(self._pointer_key(pointer_id))
            if not record:
                continue

            expires_at_utc = record.get("expires_at_utc") or None
            is_expired = self.is_expired(expires_at_utc, now_utc=now_utc)
            if not include_expired and is_expired:
                continue

            ttl_raw = record.get("ttl_seconds", "")
            ttl_seconds = int(ttl_raw) if ttl_raw else None
            metadata = json.loads(record["metadata"]) if record.get("metadata") else {}

            rows.append(
                {
                    "pointer_id": record.get("pointer_id", pointer_id),
                    "summary": record.get("summary", ""),
                    "metadata": metadata,
                    "created_at_utc": record.get("created_at_utc", ""),
                    "ttl_seconds": ttl_seconds,
                    "expires_at_utc": expires_at_utc,
                    "is_expired": is_expired,
                }
            )

        rows.sort(key=lambda row: (row["created_at_utc"], row["pointer_id"]), reverse=True)
        if limit is None:
            return rows
        return rows[:limit]

    def delete_pointer(self, pointer_id: str) -> bool:
        removed_count = self.client.delete(self._pointer_key(pointer_id))
        self.client.srem(self._pointer_ids_key, pointer_id)
        return bool(removed_count)
