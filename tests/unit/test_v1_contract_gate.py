import unittest

from scripts.check_v1_contract import evaluate_version_bump_policy


class V1ContractGatePolicyTest(unittest.TestCase):
    def test_changed_contract_without_version_bump_fails(self) -> None:
        ok, message = evaluate_version_bump_policy(
            previous_snapshot={"a": 1},
            current_snapshot={"a": 2},
            previous_package_version="0.1.7",
            current_package_version="0.1.7",
        )
        self.assertFalse(ok)
        self.assertIn("without an explicit package version bump", message)

    def test_changed_contract_with_version_bump_passes(self) -> None:
        ok, message = evaluate_version_bump_policy(
            previous_snapshot={"a": 1},
            current_snapshot={"a": 2},
            previous_package_version="0.1.7",
            current_package_version="0.1.8",
        )
        self.assertTrue(ok)
        self.assertIn("with explicit package version bump", message)

    def test_unchanged_contract_does_not_require_version_bump(self) -> None:
        ok, message = evaluate_version_bump_policy(
            previous_snapshot={"a": 1},
            current_snapshot={"a": 1},
            previous_package_version="0.1.7",
            current_package_version="0.1.7",
        )
        self.assertTrue(ok)
        self.assertIn("No contract lock change detected", message)


if __name__ == "__main__":
    unittest.main()
