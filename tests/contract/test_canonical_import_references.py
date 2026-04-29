import ast
import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
LEGACY_ROOTS = {"agent", "environment", "protocol"}
PYTHON_SCAN_ROOTS = [
    REPO_ROOT / "examples",
    REPO_ROOT / "scripts",
    REPO_ROOT / "starter_packs",
    REPO_ROOT / "tests",
]
MARKDOWN_SCAN_ROOTS = [
    REPO_ROOT / "README.md",
    REPO_ROOT / "docs",
    REPO_ROOT / "examples",
]
PYTHON_IMPORT_ALLOWLIST = {
    REPO_ROOT / "tests" / "packaging" / "test_install_smoke.py",
}
MARKDOWN_ALLOWLIST = {
    REPO_ROOT / "docs" / "upgrade_notes_v1.md",
    REPO_ROOT / "docs" / "v1_contract.md",
}
LEGACY_MARKDOWN_PATTERN = re.compile(
    r"\bfrom\s+(?:agent|environment|protocol)(?:\.|\s+import)|"
    r"\bimport\s+(?:agent|environment|protocol)(?:\.|\s|$)|"
    r"`(?:agent|environment|protocol)\."
)
LEGACY_PATCH_PATTERN = re.compile(
    r"\bpatch\(\s*['\"](?:agent|environment|protocol)\."
)


def _python_files() -> list[Path]:
    paths: list[Path] = []
    for root in PYTHON_SCAN_ROOTS:
        paths.extend(root.rglob("*.py"))
    return sorted(path for path in paths if path not in PYTHON_IMPORT_ALLOWLIST)


def _markdown_files() -> list[Path]:
    paths: list[Path] = []
    for root in MARKDOWN_SCAN_ROOTS:
        if root.is_file():
            paths.append(root)
        else:
            paths.extend(root.rglob("*.md"))
    return sorted(path for path in paths if path not in MARKDOWN_ALLOWLIST)


def _legacy_root(module_name: str | None) -> str | None:
    if not module_name:
        return None
    root = module_name.split(".", 1)[0]
    return root if root in LEGACY_ROOTS else None


def test_python_examples_scripts_and_tests_use_canonical_imports() -> None:
    failures: list[str] = []
    for path in _python_files():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    root = _legacy_root(alias.name)
                    if root:
                        failures.append(f"{path}:{node.lineno} imports legacy namespace {root!r}")
            elif isinstance(node, ast.ImportFrom):
                root = _legacy_root(node.module)
                if root:
                    failures.append(f"{path}:{node.lineno} imports legacy namespace {root!r}")

    assert not failures, "\n".join(failures)


def test_tests_patch_canonical_implementation_modules() -> None:
    failures: list[str] = []
    for path in sorted((REPO_ROOT / "tests").rglob("*.py")):
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if LEGACY_PATCH_PATTERN.search(line):
                failures.append(f"{path}:{line_number} patches a legacy shim path: {line.strip()}")

    assert not failures, "\n".join(failures)


def test_markdown_examples_use_canonical_import_references() -> None:
    failures: list[str] = []
    for path in _markdown_files():
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if LEGACY_MARKDOWN_PATTERN.search(line):
                failures.append(f"{path}:{line_number} references a legacy import path: {line.strip()}")

    assert not failures, "\n".join(failures)
