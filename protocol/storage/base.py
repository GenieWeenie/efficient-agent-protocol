from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


class PointerStoreBackend(ABC):
    """Pluggable backend contract for pointer vault operations."""

    @abstractmethod
    def initialize(self) -> None:
        """Initialize backend schema/resources."""

    @abstractmethod
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
        """Persist a pointer record."""

    @abstractmethod
    def retrieve_pointer(self, pointer_id: str) -> Any:
        """Retrieve raw pointer payload by id."""

    @abstractmethod
    def list_pointers(
        self,
        include_expired: bool = True,
        now_utc: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """List pointer records."""

    @abstractmethod
    def delete_pointer(self, pointer_id: str) -> bool:
        """Delete a pointer record. Returns True if deleted, else False."""

    @staticmethod
    def parse_now_utc(now_utc: Optional[str] = None) -> datetime:
        if now_utc is None:
            return datetime.now(timezone.utc)
        parsed = datetime.fromisoformat(now_utc)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)

    @classmethod
    def is_expired(cls, expires_at_utc: Optional[str], now_utc: Optional[str] = None) -> bool:
        if not expires_at_utc:
            return False
        now_dt = cls.parse_now_utc(now_utc)
        expires_dt = cls.parse_now_utc(expires_at_utc)
        return expires_dt <= now_dt

    def list_expired_pointers(
        self,
        now_utc: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        if limit is not None and limit <= 0:
            raise ValueError("limit must be > 0 when provided.")

        all_rows = self.list_pointers(include_expired=True, now_utc=now_utc)
        expired = [
            row
            for row in all_rows
            if self.is_expired(row.get("expires_at_utc"), now_utc=now_utc)
        ]
        if limit is None:
            return expired
        return expired[:limit]

    def cleanup_expired_pointers(
        self,
        now_utc: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> Dict[str, Any]:
        expired = self.list_expired_pointers(now_utc=now_utc, limit=limit)
        deleted_pointer_ids: List[str] = []
        for row in expired:
            pointer_id = row["pointer_id"]
            if self.delete_pointer(pointer_id):
                deleted_pointer_ids.append(pointer_id)

        remaining_expired_count = len(self.list_expired_pointers(now_utc=now_utc))
        return {
            "deleted_count": len(deleted_pointer_ids),
            "deleted_pointer_ids": deleted_pointer_ids,
            "remaining_expired_count": remaining_expired_count,
            "ran_at_utc": self.parse_now_utc(now_utc).isoformat(),
        }
