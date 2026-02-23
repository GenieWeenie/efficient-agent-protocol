#!/usr/bin/env bash
set -euo pipefail

OPENCLAW_VERSION="${1:-}"
if [[ -z "${OPENCLAW_VERSION}" ]]; then
  echo "usage: $0 <openclaw-version-tag>" >&2
  exit 1
fi

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PLUGIN_DIR="${REPO_ROOT}/integrations/openclaw/eap-runtime-plugin"
MANIFEST_PATH="${PLUGIN_DIR}/openclaw.plugin.json"
SKILLS_ROOT="${PLUGIN_DIR}/skills"

if [[ ! -f "${MANIFEST_PATH}" ]]; then
  echo "missing plugin manifest: ${MANIFEST_PATH}" >&2
  exit 1
fi

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "${TMP_DIR}"' EXIT

RAW_BASE="https://raw.githubusercontent.com/openclaw/openclaw/${OPENCLAW_VERSION}"
curl -fsSL "${RAW_BASE}/src/plugins/manifest.ts" -o "${TMP_DIR}/manifest.ts"
curl -fsSL "${RAW_BASE}/docs/plugins/manifest.md" -o "${TMP_DIR}/manifest.md"
curl -fsSL "${RAW_BASE}/docs/tools/skills.md" -o "${TMP_DIR}/skills.md"

# Guard that OpenClaw still requires manifest + config schema.
grep -Fq "plugin manifest requires id" "${TMP_DIR}/manifest.ts"
grep -Fq "plugin manifest requires configSchema" "${TMP_DIR}/manifest.ts"
grep -Fq "skills?: string[]" "${TMP_DIR}/manifest.ts"

# Guard docs still advertise the key compatibility points this plugin relies on.
grep -Fq -- "- \`id\` (string): canonical plugin id." "${TMP_DIR}/manifest.md"
grep -Fq -- "- \`configSchema\` (object): JSON Schema for plugin config (inline)." "${TMP_DIR}/manifest.md"
grep -Fq -- "- \`skills\` (array): skill directories to load (relative to the plugin root)." "${TMP_DIR}/manifest.md"
grep -Fq "SKILL.md" "${TMP_DIR}/skills.md"

python3 - "${MANIFEST_PATH}" "${SKILLS_ROOT}" <<'PY'
from __future__ import annotations

import json
import sys
from pathlib import Path

manifest_path = Path(sys.argv[1])
skills_root = Path(sys.argv[2])
manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

assert isinstance(manifest.get("id"), str) and manifest["id"], "manifest id is required"
assert isinstance(manifest.get("configSchema"), dict), "manifest configSchema must be an object"
assert isinstance(manifest.get("skills"), list) and manifest["skills"], "manifest skills list is required"

for entry in manifest["skills"]:
    assert isinstance(entry, str) and entry.startswith("./skills/"), f"invalid skills entry: {entry!r}"
    skill_dir = manifest_path.parent / entry[2:]
    skill_file = skill_dir / "SKILL.md"
    assert skill_file.exists(), f"missing skill file: {skill_file}"
    text = skill_file.read_text(encoding="utf-8")
    assert text.startswith("---\n"), f"missing frontmatter in {skill_file}"
    assert "name:" in text and "description:" in text, f"missing required metadata in {skill_file}"

for expected in (
    "eap_run_workflow",
    "eap_inspect_run",
    "eap_retry_failed_step",
    "eap_export_trace",
):
    path = skills_root / expected / "SKILL.md"
    assert path.exists(), f"expected skill missing: {path}"
PY

echo "OpenClaw interop smoke passed for ${OPENCLAW_VERSION}"
