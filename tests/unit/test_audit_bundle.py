import json
import tempfile
import unittest
from pathlib import Path

from eap.runtime.audit_bundle import (
    SIGNATURE_ALGORITHM,
    build_manifest,
    canonical_json_bytes,
    compute_manifest_digest,
    sha256_bytes,
    sha256_file,
    sign_manifest_digest,
    verify_bundle_manifest,
)


class AuditBundleUnitTest(unittest.TestCase):
    def test_build_manifest_includes_sorted_hashes_and_signature(self) -> None:
        manifest = build_manifest(
            generated_at_utc="2026-02-25T00:00:00+00:00",
            db_path="/tmp/agent_state.db",
            run_ids=["run_b", "run_a"],
            file_hashes={"b.json": "222", "a.json": "111"},
            signer_key_id="ops-kms-v1",
            signing_key="secret",
        )
        self.assertEqual(list(manifest["file_hashes"].keys()), ["a.json", "b.json"])
        self.assertIn("manifest_sha256", manifest)
        self.assertIn("signature", manifest)
        self.assertEqual(manifest["signature"]["algorithm"], SIGNATURE_ALGORITHM)
        self.assertEqual(manifest["signature"]["key_id"], "ops-kms-v1")

    def test_verify_bundle_manifest_happy_path_signed(self) -> None:
        with tempfile.TemporaryDirectory(prefix="eap-audit-unit-") as temp_dir:
            bundle_dir = Path(temp_dir)
            (bundle_dir / "artifact.json").write_text(
                json.dumps({"ok": True}, sort_keys=True),
                encoding="utf-8",
            )
            file_hashes = {"artifact.json": sha256_file(bundle_dir / "artifact.json")}
            manifest = build_manifest(
                generated_at_utc="2026-02-25T00:00:00+00:00",
                db_path="/tmp/agent_state.db",
                run_ids=["run_1"],
                file_hashes=file_hashes,
                signing_key="secret",
            )

            result = verify_bundle_manifest(
                bundle_dir=bundle_dir,
                manifest=manifest,
                signing_key="secret",
                require_signature=True,
                expected_manifest_sha256=manifest["manifest_sha256"],
            )
            self.assertTrue(result.verified)
            self.assertEqual(result.errors, [])
            self.assertTrue(result.checks["manifest_sha256"]["ok"])
            self.assertTrue(result.checks["file_hashes"]["artifact.json"]["ok"])
            self.assertTrue(result.checks["signature"]["verified"])

    def test_verify_bundle_manifest_reports_missing_and_mismatch_conditions(self) -> None:
        with tempfile.TemporaryDirectory(prefix="eap-audit-unit-") as temp_dir:
            bundle_dir = Path(temp_dir)
            (bundle_dir / "artifact.json").write_text("{\"ok\":true}", encoding="utf-8")
            file_hashes = {"artifact.json": sha256_file(bundle_dir / "artifact.json")}
            manifest = build_manifest(
                generated_at_utc="2026-02-25T00:00:00+00:00",
                db_path="/tmp/agent_state.db",
                run_ids=["run_1"],
                file_hashes=file_hashes,
            )

            # Hash mismatch for artifact file.
            (bundle_dir / "artifact.json").write_text("{\"ok\":false}", encoding="utf-8")
            mismatch = verify_bundle_manifest(bundle_dir=bundle_dir, manifest=manifest)
            self.assertFalse(mismatch.verified)
            self.assertTrue(any("file hash mismatch" in error for error in mismatch.errors))

            # Missing artifact file.
            (bundle_dir / "artifact.json").unlink()
            missing = verify_bundle_manifest(bundle_dir=bundle_dir, manifest=manifest)
            self.assertFalse(missing.verified)
            self.assertTrue(any("missing artifact file" in error for error in missing.errors))

            # Missing hash map and digest mismatch.
            malformed_manifest = dict(manifest)
            malformed_manifest["file_hashes"] = {}
            malformed_manifest["manifest_sha256"] = "wrong"
            malformed = verify_bundle_manifest(
                bundle_dir=bundle_dir,
                manifest=malformed_manifest,
                expected_manifest_sha256="expected",
            )
            self.assertFalse(malformed.verified)
            self.assertTrue(any("manifest.file_hashes" in error for error in malformed.errors))
            self.assertTrue(any("manifest_sha256 mismatch" in error for error in malformed.errors))
            self.assertTrue(any("expected value" in error for error in malformed.errors))

    def test_verify_bundle_manifest_signature_error_variants(self) -> None:
        with tempfile.TemporaryDirectory(prefix="eap-audit-unit-") as temp_dir:
            bundle_dir = Path(temp_dir)
            (bundle_dir / "artifact.json").write_text("{}", encoding="utf-8")
            file_hashes = {"artifact.json": sha256_file(bundle_dir / "artifact.json")}
            base_manifest = build_manifest(
                generated_at_utc="2026-02-25T00:00:00+00:00",
                db_path="/tmp/agent_state.db",
                run_ids=["run_1"],
                file_hashes=file_hashes,
                signing_key="secret",
            )

            no_key = verify_bundle_manifest(bundle_dir=bundle_dir, manifest=base_manifest)
            self.assertFalse(no_key.verified)
            self.assertTrue(any("no signing key" in error for error in no_key.errors))

            bad_algo_manifest = dict(base_manifest)
            bad_algo_manifest["signature"] = dict(base_manifest["signature"])
            bad_algo_manifest["signature"]["algorithm"] = "rsa"
            bad_algo = verify_bundle_manifest(
                bundle_dir=bundle_dir,
                manifest=bad_algo_manifest,
                signing_key="secret",
            )
            self.assertFalse(bad_algo.verified)
            self.assertTrue(any("unsupported signature algorithm" in error for error in bad_algo.errors))

            empty_sig_manifest = dict(base_manifest)
            empty_sig_manifest["signature"] = dict(base_manifest["signature"])
            empty_sig_manifest["signature"]["value"] = ""
            empty_sig = verify_bundle_manifest(
                bundle_dir=bundle_dir,
                manifest=empty_sig_manifest,
                signing_key="secret",
            )
            self.assertFalse(empty_sig.verified)
            self.assertTrue(any("signature.value is required" in error for error in empty_sig.errors))

            mismatch_sig_manifest = dict(base_manifest)
            mismatch_sig_manifest["signature"] = dict(base_manifest["signature"])
            mismatch_sig_manifest["signature"]["value"] = "deadbeef"
            mismatch_sig = verify_bundle_manifest(
                bundle_dir=bundle_dir,
                manifest=mismatch_sig_manifest,
                signing_key="secret",
            )
            self.assertFalse(mismatch_sig.verified)
            self.assertTrue(any("signature mismatch" in error for error in mismatch_sig.errors))

            invalid_signature_manifest = dict(base_manifest)
            invalid_signature_manifest["signature"] = "not-an-object"
            invalid_sig = verify_bundle_manifest(
                bundle_dir=bundle_dir,
                manifest=invalid_signature_manifest,
                signing_key="secret",
            )
            self.assertFalse(invalid_sig.verified)
            self.assertTrue(any("signature must be an object" in error for error in invalid_sig.errors))

            require_sig_missing = dict(base_manifest)
            require_sig_missing.pop("signature", None)
            required = verify_bundle_manifest(
                bundle_dir=bundle_dir,
                manifest=require_sig_missing,
                require_signature=True,
            )
            self.assertFalse(required.verified)
            self.assertTrue(any("signature required" in error for error in required.errors))

    def test_hash_helpers_are_deterministic(self) -> None:
        payload = {"b": 2, "a": 1}
        canonical = canonical_json_bytes(payload)
        self.assertEqual(canonical, b"{\"a\":1,\"b\":2}")
        digest = sha256_bytes(canonical)
        self.assertEqual(digest, compute_manifest_digest(payload))

        signed = sign_manifest_digest(manifest_digest=digest, signing_key="secret")
        self.assertEqual(signed, sign_manifest_digest(manifest_digest=digest, signing_key="secret"))


if __name__ == "__main__":
    unittest.main()
