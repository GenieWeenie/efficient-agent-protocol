import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

from eap.protocol import StateManager


class PointerTTLIntegrationTest(unittest.TestCase):
    def setUp(self) -> None:
        fd, self.db_path = tempfile.mkstemp(prefix="eap-pointer-ttl-", suffix=".db")
        os.close(fd)
        self.manager = StateManager(db_path=self.db_path)

    def tearDown(self) -> None:
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def _future_iso_from_pointer(self, pointer_payload: dict, delta_seconds: int) -> str:
        created_at = datetime.fromisoformat(pointer_payload["metadata"]["created_at_utc"]).astimezone(timezone.utc)
        return (created_at + timedelta(seconds=delta_seconds)).isoformat()

    def test_list_pointers_can_filter_expired_items(self) -> None:
        expiring = self.manager.store_and_point(raw_data="expire-me", summary="short", ttl_seconds=60)
        keep = self.manager.store_and_point(raw_data="keep-me", summary="long")
        future = self._future_iso_from_pointer(expiring, 61)

        all_pointers = self.manager.list_pointers(include_expired=True, now_utc=future)
        active_only = self.manager.list_pointers(include_expired=False, now_utc=future)
        all_ids = {item["pointer_id"] for item in all_pointers}
        active_ids = {item["pointer_id"] for item in active_only}

        self.assertIn(expiring["pointer_id"], all_ids)
        self.assertIn(keep["pointer_id"], all_ids)
        self.assertNotIn(expiring["pointer_id"], active_ids)
        self.assertIn(keep["pointer_id"], active_ids)

    def test_cleanup_respects_limit_and_reports_remaining(self) -> None:
        pointers = [
            self.manager.store_and_point(raw_data=f"value-{idx}", summary="expiring", ttl_seconds=60)
            for idx in range(3)
        ]
        future = self._future_iso_from_pointer(pointers[0], 61)

        first = self.manager.cleanup_expired_pointers(now_utc=future, limit=2)
        self.assertEqual(first["deleted_count"], 2)
        self.assertEqual(first["remaining_expired_count"], 1)

        second = self.manager.cleanup_expired_pointers(now_utc=future, limit=10)
        self.assertEqual(second["deleted_count"], 1)
        self.assertEqual(second["remaining_expired_count"], 0)

    def test_cleanup_is_idempotent_when_nothing_is_expired(self) -> None:
        self.manager.store_and_point(raw_data="value", summary="stable")
        report = self.manager.cleanup_expired_pointers()
        self.assertEqual(report["deleted_count"], 0)
        self.assertEqual(report["remaining_expired_count"], 0)


if __name__ == "__main__":
    unittest.main()
