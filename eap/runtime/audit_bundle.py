from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Mapping, Optional


MANIFEST_FILENAME = "manifest.json"
MANIFEST_VERSION = 1
HASH_ALGORITHM = "sha256"
SIGNATURE_ALGORITHM = "hmac-sha256"


def canonical_json_bytes(payload: Mapping[str, Any]) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 64), b""):
            digest.update(chunk)
    return digest.hexdigest()


def compute_manifest_digest(manifest_core: Mapping[str, Any]) -> str:
    return sha256_bytes(canonical_json_bytes(manifest_core))


def sign_manifest_digest(manifest_digest: str, signing_key: str) -> str:
    return hmac.new(signing_key.encode("utf-8"), manifest_digest.encode("utf-8"), hashlib.sha256).hexdigest()


def build_manifest(
    *,
    generated_at_utc: str,
    db_path: str,
    run_ids: list[str],
    file_hashes: Mapping[str, str],
    signer_key_id: Optional[str] = None,
    signing_key: Optional[str] = None,
) -> Dict[str, Any]:
    manifest_core: Dict[str, Any] = {
        "manifest_version": MANIFEST_VERSION,
        "hash_algorithm": HASH_ALGORITHM,
        "generated_at_utc": generated_at_utc,
        "db_path": db_path,
        "run_ids": list(run_ids),
        "file_hashes": dict(sorted(file_hashes.items())),
    }
    manifest_digest = compute_manifest_digest(manifest_core)
    manifest: Dict[str, Any] = dict(manifest_core)
    manifest["manifest_sha256"] = manifest_digest
    if signing_key:
        manifest["signature"] = {
            "algorithm": SIGNATURE_ALGORITHM,
            "key_id": signer_key_id or "default",
            "value": sign_manifest_digest(manifest_digest=manifest_digest, signing_key=signing_key),
        }
    return manifest


@dataclass
class VerificationResult:
    verified: bool
    checks: Dict[str, Any]
    errors: list[str]


def verify_bundle_manifest(
    *,
    bundle_dir: Path,
    manifest: Mapping[str, Any],
    signing_key: Optional[str] = None,
    require_signature: bool = False,
    expected_manifest_sha256: Optional[str] = None,
) -> VerificationResult:
    errors: list[str] = []

    file_hashes = manifest.get("file_hashes")
    if not isinstance(file_hashes, dict) or not file_hashes:
        errors.append("manifest.file_hashes must be a non-empty object.")
        file_hashes = {}

    manifest_core = {
        "manifest_version": manifest.get("manifest_version"),
        "hash_algorithm": manifest.get("hash_algorithm"),
        "generated_at_utc": manifest.get("generated_at_utc"),
        "db_path": manifest.get("db_path"),
        "run_ids": manifest.get("run_ids"),
        "file_hashes": dict(sorted((str(k), str(v)) for k, v in file_hashes.items())),
    }
    computed_manifest_digest = compute_manifest_digest(manifest_core)
    manifest_digest = str(manifest.get("manifest_sha256", ""))
    if not manifest_digest:
        errors.append("manifest.manifest_sha256 is required.")
    elif manifest_digest != computed_manifest_digest:
        errors.append("manifest.manifest_sha256 mismatch.")

    if expected_manifest_sha256 and manifest_digest != expected_manifest_sha256:
        errors.append("manifest.manifest_sha256 did not match expected value.")

    file_results: Dict[str, Any] = {}
    for filename, expected_hash in sorted(file_hashes.items()):
        path = bundle_dir / str(filename)
        if not path.exists() or not path.is_file():
            errors.append(f"missing artifact file: {filename}")
            file_results[str(filename)] = {"ok": False, "reason": "missing"}
            continue
        actual_hash = sha256_file(path)
        ok = actual_hash == str(expected_hash)
        file_results[str(filename)] = {
            "ok": ok,
            "expected_sha256": str(expected_hash),
            "actual_sha256": actual_hash,
        }
        if not ok:
            errors.append(f"file hash mismatch: {filename}")

    signature = manifest.get("signature")
    signature_ok: Optional[bool] = None
    if signature is None:
        signature_ok = None
        if require_signature:
            errors.append("manifest signature required but not present.")
    else:
        if not isinstance(signature, dict):
            signature_ok = False
            errors.append("manifest.signature must be an object.")
        else:
            signature_algorithm = str(signature.get("algorithm", ""))
            signature_value = str(signature.get("value", ""))
            if signature_algorithm != SIGNATURE_ALGORITHM:
                errors.append(
                    f"unsupported signature algorithm '{signature_algorithm}', expected '{SIGNATURE_ALGORITHM}'."
                )
                signature_ok = False
            elif not signature_value:
                errors.append("manifest.signature.value is required.")
                signature_ok = False
            elif not signing_key:
                errors.append("manifest is signed but no signing key was provided for verification.")
                signature_ok = False
            else:
                expected_signature = sign_manifest_digest(
                    manifest_digest=manifest_digest,
                    signing_key=signing_key,
                )
                signature_ok = hmac.compare_digest(signature_value, expected_signature)
                if not signature_ok:
                    errors.append("manifest signature mismatch.")

    checks = {
        "manifest_sha256": {
            "ok": bool(manifest_digest) and manifest_digest == computed_manifest_digest,
            "expected": manifest_digest,
            "actual": computed_manifest_digest,
        },
        "file_hashes": file_results,
        "signature": {
            "present": signature is not None,
            "verified": signature_ok,
            "required": require_signature,
        },
    }

    return VerificationResult(
        verified=not errors,
        checks=checks,
        errors=errors,
    )
