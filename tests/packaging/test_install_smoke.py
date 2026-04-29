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
        with tempfile.TemporaryDirectory(prefix="eap-dist-") as tmpdir:
            dist_dir = pathlib.Path(tmpdir) / "dist"
            _run(
                [
                    sys.executable,
                    "-m",
                    "build",
                    "--sdist",
                    "--wheel",
                    "--outdir",
                    str(dist_dir),
                ],
                cwd=PROJECT_ROOT,
            )
            wheel = self._single_artifact(dist_dir, "*.whl")
            sdist = self._single_artifact(dist_dir, "*.tar.gz")

            self._assert_install_mode([str(wheel)])
            self._assert_install_mode([str(sdist)])
        self._assert_install_mode(["-e", str(PROJECT_ROOT)])

    def _single_artifact(self, dist_dir: pathlib.Path, pattern: str) -> pathlib.Path:
        matches = sorted(dist_dir.glob(pattern))
        if len(matches) != 1:
            raise AssertionError(
                f"Expected exactly one artifact for {pattern}, found {[str(path) for path in matches]}"
            )
        return matches[0]

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
                        "from pathlib import Path; "
                        "import eap.agent.providers.openai_provider as canonical_openai_provider; "
                        "import agent.agent_client as legacy_agent_client; "
                        "import environment.executor as legacy_executor; "
                        "import protocol.state_manager as legacy_state_manager; "
                        "import eap.agent.agent_client as canonical_agent_client; "
                        "import eap.environment.executor as canonical_executor; "
                        "import eap.environment.tools.web_tools as canonical_web_tools; "
                        "import eap.protocol.state_manager as canonical_state_manager; "
                        "import eap.protocol.storage.sqlite_store as canonical_sqlite_store; "
                        "assert canonical_openai_provider.OpenAIProvider; "
                        "assert canonical_web_tools.scrape_url; "
                        "assert canonical_sqlite_store.SQLitePointerStore; "
                        "assert legacy_agent_client.AgentClient is canonical_agent_client.AgentClient; "
                        "assert legacy_executor.AsyncLocalExecutor is canonical_executor.AsyncLocalExecutor; "
                        "assert legacy_state_manager.StateManager is canonical_state_manager.StateManager; "
                        "assert 'Compatibility shim' in Path(legacy_agent_client.__file__).read_text(); "
                        "assert 'Compatibility shim' in Path(legacy_executor.__file__).read_text(); "
                        "assert 'Compatibility shim' in Path(legacy_state_manager.__file__).read_text(); "
                        "print('import-smoke-ok')"
                    ),
                ]
            )


if __name__ == "__main__":
    unittest.main()
