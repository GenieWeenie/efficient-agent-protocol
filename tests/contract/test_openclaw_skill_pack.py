from __future__ import annotations

import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
PLUGIN_DIR = REPO_ROOT / "integrations" / "openclaw" / "eap-runtime-plugin"
MANIFEST_PATH = PLUGIN_DIR / "openclaw.plugin.json"
SKILL_ROOT = PLUGIN_DIR / "skills"
EXPECTED_SKILLS = (
    "eap_run_workflow",
    "eap_inspect_run",
    "eap_retry_failed_step",
    "eap_export_trace",
)


def test_openclaw_manifest_declares_skill_directories() -> None:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    assert "skills" in manifest
    manifest_skills = tuple(manifest["skills"])
    expected_paths = tuple(f"./skills/{name}" for name in EXPECTED_SKILLS)
    assert manifest_skills == expected_paths


def test_skill_pack_contains_expected_skill_files() -> None:
    for skill_name in EXPECTED_SKILLS:
        skill_file = SKILL_ROOT / skill_name / "SKILL.md"
        assert skill_file.exists(), f"missing skill file: {skill_file}"
        content = skill_file.read_text(encoding="utf-8")
        assert content.startswith("---\n"), f"missing frontmatter in {skill_file}"
        assert f"name: {skill_name}" in content, f"missing name frontmatter in {skill_file}"
        assert "description:" in content, f"missing description frontmatter in {skill_file}"
