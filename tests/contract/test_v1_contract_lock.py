import json
import unittest
from pathlib import Path

from scripts.check_v1_contract import build_current_snapshot


REPO_ROOT = Path(__file__).resolve().parents[2]
LOCK_PATH = REPO_ROOT / "docs" / "v1_contract_lock.json"


class V1ContractLockTest(unittest.TestCase):
    def test_lock_file_exists_and_has_required_metadata(self) -> None:
        self.assertTrue(LOCK_PATH.exists(), "docs/v1_contract_lock.json must exist")
        payload = json.loads(LOCK_PATH.read_text(encoding="utf-8"))
        self.assertEqual(payload.get("lock_format_version"), 1)
        self.assertEqual(payload.get("snapshot_version"), "1.0.0")
        self.assertIn("generated_from_package_version", payload)
        self.assertIsInstance(payload.get("snapshot"), dict)

    def test_lock_snapshot_matches_current_runtime_surface(self) -> None:
        payload = json.loads(LOCK_PATH.read_text(encoding="utf-8"))
        expected_snapshot = payload["snapshot"]
        current_snapshot = build_current_snapshot(REPO_ROOT)
        self.assertDictEqual(current_snapshot, expected_snapshot)


if __name__ == "__main__":
    unittest.main()
