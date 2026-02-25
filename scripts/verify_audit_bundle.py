#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from eap.runtime.audit_bundle import MANIFEST_FILENAME, verify_bundle_manifest


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Verify audit bundle file hashes and optional manifest signature."
    )
    parser.add_argument(
        "--bundle-dir",
        required=True,
        help="Audit bundle directory containing manifest.json and artifact files.",
    )
    parser.add_argument(
        "--signing-key",
        default=None,
        help="HMAC verification key. Falls back to EAP_AUDIT_SIGNING_KEY when omitted.",
    )
    parser.add_argument(
        "--require-signature",
        action="store_true",
        help="Fail verification when manifest signature is missing.",
    )
    parser.add_argument(
        "--expected-manifest-sha256",
        default=None,
        help="Optional expected manifest digest trust anchor.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    bundle_dir = Path(args.bundle_dir)
    manifest_path = bundle_dir / MANIFEST_FILENAME
    if not manifest_path.exists():
        print(
            json.dumps(
                {
                    "verified": False,
                    "errors": [f"missing manifest file: {manifest_path}"],
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 1

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(
            json.dumps(
                {
                    "verified": False,
                    "errors": [f"invalid manifest json: {exc}"],
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 1

    signing_key = args.signing_key or os.getenv("EAP_AUDIT_SIGNING_KEY")
    result = verify_bundle_manifest(
        bundle_dir=bundle_dir,
        manifest=manifest,
        signing_key=signing_key,
        require_signature=args.require_signature,
        expected_manifest_sha256=args.expected_manifest_sha256,
    )
    payload = {
        "verified": result.verified,
        "errors": result.errors,
        "checks": result.checks,
    }
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if result.verified else 1


if __name__ == "__main__":
    raise SystemExit(main())
