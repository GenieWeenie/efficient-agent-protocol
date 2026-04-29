from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
LEGACY_PACKAGE_ROOTS = [
    REPO_ROOT / "agent",
    REPO_ROOT / "environment",
    REPO_ROOT / "protocol",
]


def test_legacy_top_level_modules_are_compatibility_shims() -> None:
    for package_root in LEGACY_PACKAGE_ROOTS:
        for module_path in package_root.rglob("*.py"):
            text = module_path.read_text(encoding="utf-8")
            assert "Compatibility" in text, f"{module_path} is not marked as a compatibility shim"
            if module_path in {root / "__init__.py" for root in LEGACY_PACKAGE_ROOTS}:
                assert "importlib.import_module" in text, f"{module_path} does not route through canonical modules"
            else:
                relative_path = module_path.with_suffix("").relative_to(REPO_ROOT)
                if relative_path.name == "__init__":
                    relative_path = relative_path.parent
                relative_module = relative_path.as_posix().replace("/", ".")
                assert f"from eap.{relative_module} import *" in text, (
                    f"{module_path} does not re-export from eap.{relative_module}"
                )


def test_canonical_eap_modules_do_not_import_legacy_namespaces() -> None:
    forbidden_prefixes = (
        "from agent",
        "from environment",
        "from protocol",
        "import agent",
        "import environment",
        "import protocol",
    )
    for module_path in (REPO_ROOT / "eap").rglob("*.py"):
        text = module_path.read_text(encoding="utf-8")
        for line in text.splitlines():
            stripped = line.strip()
            assert not stripped.startswith(forbidden_prefixes), (
                f"{module_path} imports a legacy namespace: {stripped}"
            )
