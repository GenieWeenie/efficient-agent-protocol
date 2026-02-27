"""Contract tests for pointer lifecycle semantics frozen in v1.

These tests verify the pointer TTL, expiry evaluation, listing,
retrieval, deletion, and cleanup behaviors documented in
docs/v1_contract.md under "Pointer Lifecycle Contract (Frozen)".
"""
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

from eap.protocol import StateManager


class PointerCreationContractTest(unittest.TestCase):
    def setUp(self) -> None:
        fd, self.db_path = tempfile.mkstemp(prefix="eap-lifecycle-contract-", suffix=".db")
        os.close(fd)
        self.sm = StateManager(db_path=self.db_path)

    def tearDown(self) -> None:
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def test_pointer_without_ttl_never_expires(self) -> None:
        result = self.sm.store_and_point("data", "summary")
        pointer_id = result["pointer_id"]
        pointers = self.sm.list_pointers(include_expired=True)
        match = next(p for p in pointers if p["pointer_id"] == pointer_id)
        self.assertFalse(match["is_expired"])
        self.assertIsNone(match.get("ttl_seconds"))
        self.assertIsNone(match.get("expires_at_utc"))

    def test_pointer_with_ttl_sets_lifecycle_fields(self) -> None:
        result = self.sm.store_and_point("data", "summary", ttl_seconds=300)
        pointer_id = result["pointer_id"]
        pointers = self.sm.list_pointers(include_expired=True)
        match = next(p for p in pointers if p["pointer_id"] == pointer_id)
        self.assertEqual(match["ttl_seconds"], 300)
        self.assertIsNotNone(match["created_at_utc"])
        self.assertIsNotNone(match["expires_at_utc"])
        created = datetime.fromisoformat(match["created_at_utc"])
        expires = datetime.fromisoformat(match["expires_at_utc"])
        self.assertAlmostEqual((expires - created).total_seconds(), 300, delta=2)

    def test_ttl_minimum_boundary_value_1(self) -> None:
        result = self.sm.store_and_point("data", "summary", ttl_seconds=1)
        self.assertIn("pointer_id", result)

    def test_ttl_zero_raises_value_error(self) -> None:
        with self.assertRaises(ValueError):
            self.sm.store_and_point("data", "summary", ttl_seconds=0)

    def test_ttl_negative_raises_value_error(self) -> None:
        with self.assertRaises(ValueError):
            self.sm.store_and_point("data", "summary", ttl_seconds=-10)

    def test_ttl_boolean_raises_value_error(self) -> None:
        with self.assertRaises(ValueError):
            self.sm.store_and_point("data", "summary", ttl_seconds=True)

    def test_ttl_float_raises_value_error(self) -> None:
        with self.assertRaises((ValueError, TypeError)):
            self.sm.store_and_point("data", "summary", ttl_seconds=3.5)  # type: ignore[arg-type]

    def test_pointer_id_format(self) -> None:
        result = self.sm.store_and_point("data", "summary")
        self.assertTrue(result["pointer_id"].startswith("ptr_"))
        self.assertEqual(len(result["pointer_id"]), 12)  # "ptr_" + 8 hex chars

    def test_metadata_includes_lifecycle_and_size(self) -> None:
        result = self.sm.store_and_point("hello", "summary", ttl_seconds=60)
        meta = result["metadata"]
        self.assertIn("size_bytes", meta)
        self.assertIn("created_at_utc", meta)
        self.assertIn("ttl_seconds", meta)
        self.assertIn("expires_at_utc", meta)
        self.assertEqual(meta["ttl_seconds"], 60)


class PointerExpiryEvaluationContractTest(unittest.TestCase):
    def setUp(self) -> None:
        fd, self.db_path = tempfile.mkstemp(prefix="eap-expiry-contract-", suffix=".db")
        os.close(fd)
        self.sm = StateManager(db_path=self.db_path)

    def tearDown(self) -> None:
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def test_expired_at_exact_boundary(self) -> None:
        """Pointer is expired when expires_at_utc == now_utc (inclusive)."""
        result = self.sm.store_and_point("data", "summary", ttl_seconds=60)
        pointer_id = result["pointer_id"]
        expires_at = result["metadata"]["expires_at_utc"]

        pointers = self.sm.list_pointers(include_expired=True, now_utc=expires_at)
        match = next(p for p in pointers if p["pointer_id"] == pointer_id)
        self.assertTrue(match["is_expired"])

    def test_not_expired_one_second_before_boundary(self) -> None:
        result = self.sm.store_and_point("data", "summary", ttl_seconds=60)
        pointer_id = result["pointer_id"]
        expires_at = datetime.fromisoformat(result["metadata"]["expires_at_utc"])
        one_second_before = (expires_at - timedelta(seconds=1)).isoformat()

        pointers = self.sm.list_pointers(include_expired=True, now_utc=one_second_before)
        match = next(p for p in pointers if p["pointer_id"] == pointer_id)
        self.assertFalse(match["is_expired"])

    def test_expired_one_second_after_boundary(self) -> None:
        result = self.sm.store_and_point("data", "summary", ttl_seconds=60)
        pointer_id = result["pointer_id"]
        expires_at = datetime.fromisoformat(result["metadata"]["expires_at_utc"])
        one_second_after = (expires_at + timedelta(seconds=1)).isoformat()

        pointers = self.sm.list_pointers(include_expired=True, now_utc=one_second_after)
        match = next(p for p in pointers if p["pointer_id"] == pointer_id)
        self.assertTrue(match["is_expired"])


class PointerListingContractTest(unittest.TestCase):
    def setUp(self) -> None:
        fd, self.db_path = tempfile.mkstemp(prefix="eap-listing-contract-", suffix=".db")
        os.close(fd)
        self.sm = StateManager(db_path=self.db_path)

    def tearDown(self) -> None:
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def test_include_expired_true_returns_all(self) -> None:
        self.sm.store_and_point("permanent", "summary")
        self.sm.store_and_point("expiring", "summary", ttl_seconds=1)
        far_future = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()

        all_pointers = self.sm.list_pointers(include_expired=True, now_utc=far_future)
        self.assertEqual(len(all_pointers), 2)

    def test_include_expired_false_filters_expired(self) -> None:
        perm = self.sm.store_and_point("permanent", "permanent-summary")
        self.sm.store_and_point("expiring", "expiring-summary", ttl_seconds=1)
        far_future = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()

        active_pointers = self.sm.list_pointers(include_expired=False, now_utc=far_future)
        self.assertEqual(len(active_pointers), 1)
        self.assertEqual(active_pointers[0]["pointer_id"], perm["pointer_id"])

    def test_is_expired_field_always_present(self) -> None:
        self.sm.store_and_point("data", "summary")
        self.sm.store_and_point("data", "summary", ttl_seconds=60)
        for p in self.sm.list_pointers(include_expired=True):
            self.assertIn("is_expired", p)

    def test_list_ordering_newest_first(self) -> None:
        r1 = self.sm.store_and_point("first", "first")
        r2 = self.sm.store_and_point("second", "second")
        pointers = self.sm.list_pointers(include_expired=True)
        self.assertEqual(pointers[0]["pointer_id"], r2["pointer_id"])
        self.assertEqual(pointers[1]["pointer_id"], r1["pointer_id"])

    def test_list_limit_positive(self) -> None:
        for i in range(5):
            self.sm.store_and_point(f"data{i}", f"summary{i}")
        pointers = self.sm.list_pointers(include_expired=True, limit=3)
        self.assertEqual(len(pointers), 3)

    def test_list_expired_pointers_only_returns_expired(self) -> None:
        self.sm.store_and_point("permanent", "permanent")
        self.sm.store_and_point("expiring", "expiring", ttl_seconds=1)
        far_future = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()

        expired = self.sm.list_expired_pointers(now_utc=far_future)
        self.assertEqual(len(expired), 1)
        self.assertEqual(expired[0]["summary"], "expiring")


class PointerRetrievalContractTest(unittest.TestCase):
    def setUp(self) -> None:
        fd, self.db_path = tempfile.mkstemp(prefix="eap-retrieval-contract-", suffix=".db")
        os.close(fd)
        self.sm = StateManager(db_path=self.db_path)

    def tearDown(self) -> None:
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def test_retrieve_returns_raw_payload(self) -> None:
        result = self.sm.store_and_point("hello world", "summary")
        payload = self.sm.retrieve(result["pointer_id"])
        self.assertEqual(payload, "hello world")

    def test_retrieve_expired_pointer_still_works(self) -> None:
        """Expired pointers remain retrievable until explicitly deleted."""
        result = self.sm.store_and_point("data", "summary", ttl_seconds=1)
        pointer_id = result["pointer_id"]
        far_future = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
        expired = self.sm.list_expired_pointers(now_utc=far_future)
        self.assertEqual(len(expired), 1)

        payload = self.sm.retrieve(pointer_id)
        self.assertEqual(payload, "data")

    def test_retrieve_missing_pointer_raises_key_error(self) -> None:
        with self.assertRaises(KeyError):
            self.sm.retrieve("ptr_nonexist")


class PointerDeletionContractTest(unittest.TestCase):
    def setUp(self) -> None:
        fd, self.db_path = tempfile.mkstemp(prefix="eap-deletion-contract-", suffix=".db")
        os.close(fd)
        self.sm = StateManager(db_path=self.db_path)

    def tearDown(self) -> None:
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def test_delete_removes_pointer(self) -> None:
        result = self.sm.store_and_point("data", "summary")
        pointer_id = result["pointer_id"]
        self.sm.delete_pointer(pointer_id)
        with self.assertRaises(KeyError):
            self.sm.retrieve(pointer_id)

    def test_delete_missing_pointer_raises_key_error(self) -> None:
        with self.assertRaises(KeyError):
            self.sm.delete_pointer("ptr_nonexist")


class PointerCleanupContractTest(unittest.TestCase):
    def setUp(self) -> None:
        fd, self.db_path = tempfile.mkstemp(prefix="eap-cleanup-contract-", suffix=".db")
        os.close(fd)
        self.sm = StateManager(db_path=self.db_path)

    def tearDown(self) -> None:
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def test_cleanup_deletes_expired_and_preserves_permanent(self) -> None:
        perm = self.sm.store_and_point("permanent", "permanent")
        self.sm.store_and_point("expiring", "expiring", ttl_seconds=1)
        far_future = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()

        report = self.sm.cleanup_expired_pointers(now_utc=far_future)
        self.assertEqual(report["deleted_count"], 1)
        self.assertEqual(len(report["deleted_pointer_ids"]), 1)
        self.assertEqual(report["remaining_expired_count"], 0)
        self.assertIn("ran_at_utc", report)

        self.assertEqual(self.sm.retrieve(perm["pointer_id"]), "permanent")

    def test_cleanup_idempotent_with_nothing_expired(self) -> None:
        self.sm.store_and_point("data", "summary")
        report = self.sm.cleanup_expired_pointers()
        self.assertEqual(report["deleted_count"], 0)
        self.assertEqual(report["deleted_pointer_ids"], [])
        self.assertEqual(report["remaining_expired_count"], 0)

    def test_cleanup_respects_limit(self) -> None:
        for i in range(3):
            self.sm.store_and_point(f"data{i}", f"summary{i}", ttl_seconds=1)
        far_future = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()

        report = self.sm.cleanup_expired_pointers(now_utc=far_future, limit=2)
        self.assertEqual(report["deleted_count"], 2)
        self.assertEqual(report["remaining_expired_count"], 1)

        report2 = self.sm.cleanup_expired_pointers(now_utc=far_future)
        self.assertEqual(report2["deleted_count"], 1)
        self.assertEqual(report2["remaining_expired_count"], 0)

    def test_cleanup_never_deletes_non_expired(self) -> None:
        perm1 = self.sm.store_and_point("data1", "summary1")
        perm2 = self.sm.store_and_point("data2", "summary2")
        far_future = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()

        report = self.sm.cleanup_expired_pointers(now_utc=far_future)
        self.assertEqual(report["deleted_count"], 0)
        self.assertEqual(self.sm.retrieve(perm1["pointer_id"]), "data1")
        self.assertEqual(self.sm.retrieve(perm2["pointer_id"]), "data2")

    def test_cleanup_report_structure(self) -> None:
        self.sm.store_and_point("data", "summary", ttl_seconds=1)
        far_future = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()

        report = self.sm.cleanup_expired_pointers(now_utc=far_future)
        self.assertIn("deleted_count", report)
        self.assertIn("deleted_pointer_ids", report)
        self.assertIn("remaining_expired_count", report)
        self.assertIn("ran_at_utc", report)
        self.assertIsInstance(report["deleted_count"], int)
        self.assertIsInstance(report["deleted_pointer_ids"], list)
        self.assertIsInstance(report["remaining_expired_count"], int)
        self.assertIsInstance(report["ran_at_utc"], str)


if __name__ == "__main__":
    unittest.main()
