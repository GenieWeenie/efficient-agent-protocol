import os
import tempfile
import unittest
from typing import Any, Dict, List, Optional

from eap.protocol import (
    PointerStoreBackend,
    PostgresPointerStore,
    RedisPointerStore,
    StateManager,
)


class InMemoryPointerStore(PointerStoreBackend):
    def __init__(self) -> None:
        self.rows: Dict[str, Dict[str, Any]] = {}

    def initialize(self) -> None:
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
        self.rows[pointer_id] = {
            "pointer_id": pointer_id,
            "raw_data": raw_data,
            "summary": summary,
            "metadata": dict(metadata),
            "created_at_utc": created_at_utc,
            "ttl_seconds": ttl_seconds,
            "expires_at_utc": expires_at_utc,
        }

    def retrieve_pointer(self, pointer_id: str) -> Any:
        row = self.rows.get(pointer_id)
        if row is None:
            raise KeyError(f"Pointer {pointer_id} not found in persistent storage.")
        return row["raw_data"]

    def list_pointers(
        self,
        include_expired: bool = True,
        now_utc: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        if limit is not None and limit <= 0:
            raise ValueError("limit must be > 0 when provided.")

        rows = sorted(
            self.rows.values(),
            key=lambda row: (row["created_at_utc"], row["pointer_id"]),
            reverse=True,
        )
        pointer_rows: List[Dict[str, Any]] = []
        for row in rows:
            is_expired = self.is_expired(row.get("expires_at_utc"), now_utc=now_utc)
            if not include_expired and is_expired:
                continue
            pointer_rows.append(
                {
                    "pointer_id": row["pointer_id"],
                    "summary": row["summary"],
                    "metadata": dict(row["metadata"]),
                    "created_at_utc": row["created_at_utc"],
                    "ttl_seconds": row["ttl_seconds"],
                    "expires_at_utc": row["expires_at_utc"],
                    "is_expired": is_expired,
                }
            )
        if limit is None:
            return pointer_rows
        return pointer_rows[:limit]

    def delete_pointer(self, pointer_id: str) -> bool:
        return self.rows.pop(pointer_id, None) is not None


class FakeRedisClient:
    def __init__(self) -> None:
        self.hashes: Dict[str, Dict[str, str]] = {}
        self.sets: Dict[str, set[str]] = {}

    def hset(self, key: str, mapping: Dict[str, str]) -> int:
        bucket = self.hashes.setdefault(key, {})
        before = len(bucket)
        for map_key, value in mapping.items():
            bucket[map_key] = value
        return len(bucket) - before

    def hget(self, key: str, field: str) -> Optional[str]:
        return self.hashes.get(key, {}).get(field)

    def hgetall(self, key: str) -> Dict[str, str]:
        return dict(self.hashes.get(key, {}))

    def sadd(self, key: str, *members: str) -> int:
        member_set = self.sets.setdefault(key, set())
        before = len(member_set)
        member_set.update(members)
        return len(member_set) - before

    def smembers(self, key: str) -> set[str]:
        return set(self.sets.get(key, set()))

    def srem(self, key: str, *members: str) -> int:
        member_set = self.sets.get(key, set())
        removed = 0
        for member in members:
            if member in member_set:
                member_set.remove(member)
                removed += 1
        return removed

    def delete(self, key: str) -> int:
        if key in self.hashes:
            del self.hashes[key]
            return 1
        return 0


class FakePostgresPointerClient:
    def __init__(self) -> None:
        self.rows: Dict[str, Dict[str, Any]] = {}

    def initialize(self) -> None:
        return None

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
        self.rows[pointer_id] = {
            "pointer_id": pointer_id,
            "raw_data": raw_data,
            "summary": summary,
            "metadata": dict(metadata),
            "created_at_utc": created_at_utc,
            "ttl_seconds": ttl_seconds,
            "expires_at_utc": expires_at_utc,
        }

    def retrieve_pointer(self, pointer_id: str) -> Any:
        row = self.rows.get(pointer_id)
        if row is None:
            raise KeyError(f"Pointer {pointer_id} not found in persistent storage.")
        return row["raw_data"]

    def list_pointers(
        self,
        include_expired: bool = True,
        now_utc: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        if limit is not None and limit <= 0:
            raise ValueError("limit must be > 0 when provided.")

        rows = sorted(
            self.rows.values(),
            key=lambda row: (row["created_at_utc"], row["pointer_id"]),
            reverse=True,
        )
        pointer_rows: List[Dict[str, Any]] = []
        for row in rows:
            is_expired = PointerStoreBackend.is_expired(row.get("expires_at_utc"), now_utc=now_utc)
            if not include_expired and is_expired:
                continue
            pointer_rows.append(
                {
                    "pointer_id": row["pointer_id"],
                    "summary": row["summary"],
                    "metadata": dict(row["metadata"]),
                    "created_at_utc": row["created_at_utc"],
                    "ttl_seconds": row["ttl_seconds"],
                    "expires_at_utc": row["expires_at_utc"],
                    "is_expired": is_expired,
                }
            )
        if limit is None:
            return pointer_rows
        return pointer_rows[:limit]

    def delete_pointer(self, pointer_id: str) -> bool:
        return self.rows.pop(pointer_id, None) is not None


class PointerStoreContractMixin:
    def build_store(self) -> PointerStoreBackend:
        raise NotImplementedError

    def setUp(self) -> None:
        self.store = self.build_store()
        self.store.initialize()

    def test_store_retrieve_list_delete_contract(self) -> None:
        self.store.store_pointer(
            pointer_id="ptr_a",
            raw_data="value-a",
            summary="A",
            metadata={"k": "a"},
            created_at_utc="2026-02-23T00:00:00+00:00",
            ttl_seconds=None,
            expires_at_utc=None,
        )
        self.store.store_pointer(
            pointer_id="ptr_b",
            raw_data="value-b",
            summary="B",
            metadata={"k": "b"},
            created_at_utc="2026-02-23T00:00:01+00:00",
            ttl_seconds=60,
            expires_at_utc="2026-02-23T00:01:01+00:00",
        )

        rows = self.store.list_pointers(limit=10)
        self.assertEqual([row["pointer_id"] for row in rows], ["ptr_b", "ptr_a"])
        self.assertEqual(self.store.retrieve_pointer("ptr_a"), "value-a")
        self.assertTrue(self.store.delete_pointer("ptr_a"))
        self.assertFalse(self.store.delete_pointer("ptr_missing"))

    def test_default_expired_listing_and_cleanup_helpers(self) -> None:
        now_utc = "2026-02-23T00:10:00+00:00"
        self.store.store_pointer(
            pointer_id="ptr_keep",
            raw_data="value-keep",
            summary="keep",
            metadata={},
            created_at_utc="2026-02-23T00:00:00+00:00",
            ttl_seconds=None,
            expires_at_utc=None,
        )
        self.store.store_pointer(
            pointer_id="ptr_expire",
            raw_data="value-expire",
            summary="expire",
            metadata={},
            created_at_utc="2026-02-23T00:00:01+00:00",
            ttl_seconds=60,
            expires_at_utc="2026-02-23T00:01:01+00:00",
        )

        expired_before = self.store.list_expired_pointers(now_utc=now_utc)
        self.assertEqual([item["pointer_id"] for item in expired_before], ["ptr_expire"])

        report = self.store.cleanup_expired_pointers(now_utc=now_utc)
        self.assertEqual(report["deleted_count"], 1)
        self.assertEqual(report["deleted_pointer_ids"], ["ptr_expire"])
        self.assertEqual(report["remaining_expired_count"], 0)
        self.assertEqual(self.store.retrieve_pointer("ptr_keep"), "value-keep")


class InMemoryPointerStoreContractTest(PointerStoreContractMixin, unittest.TestCase):
    def build_store(self) -> PointerStoreBackend:
        return InMemoryPointerStore()


class RedisPointerStoreContractTest(PointerStoreContractMixin, unittest.TestCase):
    def build_store(self) -> PointerStoreBackend:
        return RedisPointerStore(client=FakeRedisClient(), key_prefix="eap:test:store")


class PostgresPointerStoreContractTest(PointerStoreContractMixin, unittest.TestCase):
    def build_store(self) -> PointerStoreBackend:
        return PostgresPointerStore(client=FakePostgresPointerClient())


class StateManagerStorageInjectionTest(unittest.TestCase):
    def test_state_manager_uses_injected_pointer_backend(self) -> None:
        fd, db_path = tempfile.mkstemp(prefix="eap-injected-store-", suffix=".db")
        os.close(fd)
        self.addCleanup(lambda: os.path.exists(db_path) and os.remove(db_path))

        injected = InMemoryPointerStore()
        manager = StateManager(db_path=db_path, pointer_store=injected)
        pointer = manager.store_and_point(raw_data={"ok": True}, summary="injected")
        self.assertIn(pointer["pointer_id"], injected.rows)
        self.assertEqual(manager.retrieve(pointer["pointer_id"]), "{'ok': True}")

        manager.delete_pointer(pointer["pointer_id"])
        with self.assertRaises(KeyError):
            manager.retrieve(pointer["pointer_id"])


if __name__ == "__main__":
    unittest.main()
