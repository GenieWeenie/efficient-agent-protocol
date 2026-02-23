import os
import pathlib
import subprocess
import sys
import tempfile
import unittest
from typing import List, Optional


PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[2]


def _venv_python(venv_path: pathlib.Path) -> pathlib.Path:
    bin_dir = "Scripts" if os.name == "nt" else "bin"
    return venv_path / bin_dir / "python"


def _run(cmd: List[str], cwd: Optional[pathlib.Path] = None) -> str:
    result = subprocess.run(
        cmd,
        cwd=str(cwd) if cwd else None,
        text=True,
        capture_output=True,
    )
    if result.returncode != 0:
        raise AssertionError(
            f"Command failed: {' '.join(cmd)}\n"
            f"stdout:\n{result.stdout}\n"
            f"stderr:\n{result.stderr}"
        )
    return result.stdout


class InstallSmokeTest(unittest.TestCase):
    @unittest.skipUnless(
        os.environ.get("RUN_PACKAGING_SMOKE") == "1",
        "Set RUN_PACKAGING_SMOKE=1 to run packaging smoke tests.",
    )
    def test_standard_and_editable_installs(self) -> None:
        self._assert_install_mode([str(PROJECT_ROOT)])
        self._assert_install_mode(["-e", str(PROJECT_ROOT)])

    def _assert_install_mode(self, install_args: List[str]) -> None:
        with tempfile.TemporaryDirectory(prefix="eap-smoke-") as tmpdir:
            venv_dir = pathlib.Path(tmpdir) / "venv"
            _run([sys.executable, "-m", "venv", str(venv_dir)], cwd=PROJECT_ROOT)
            python = _venv_python(venv_dir)

            # Ensure modern pip supports PEP 517/660 workflows.
            _run([str(python), "-m", "pip", "install", "--upgrade", "pip"])
            _run([str(python), "-m", "pip", "install", *install_args], cwd=PROJECT_ROOT)

            _run(
                [
                    str(python),
                    "-c",
                    (
                        "import eap; "
                        "from eap.protocol import StateManager; "
                        "from eap.environment import AsyncLocalExecutor, ToolRegistry; "
                        "from eap.agent import AgentClient; "
                        "print('import-smoke-ok')"
                    ),
                ]
            )


if __name__ == "__main__":
    unittest.main()
