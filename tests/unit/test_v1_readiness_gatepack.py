import subprocess

from scripts import v1_readiness_gatepack as gatepack


def _completed(returncode: int, stdout: str = "", stderr: str = "") -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr=stderr)


def test_security_audit_falls_back_to_local_audit_on_ensurepip_abort(monkeypatch) -> None:
    calls: list[list[str]] = []

    def fake_run(cmd: list[str], timeout: int = 120) -> subprocess.CompletedProcess[str]:
        calls.append(cmd)
        if cmd[-1] == "--version":
            return _completed(0, stdout="pip-audit 2.10.0")
        if "-r" in cmd:
            return _completed(
                1,
                stderr="subprocess.CalledProcessError: ensurepip died with <Signals.SIGABRT: 6>",
            )
        if cmd[-1] == "--local":
            return _completed(0, stdout="No known vulnerabilities found")
        return _completed(1, stderr="unexpected command")

    monkeypatch.setattr(gatepack, "_run", fake_run)

    result = gatepack.gate_security_audit()

    assert result.passed is True
    assert "local environment audit" in result.detail
    assert any(cmd[-1] == "--local" for cmd in calls)


def test_security_audit_fails_when_requirements_and_fallback_fail(monkeypatch) -> None:
    def fake_run(cmd: list[str], timeout: int = 120) -> subprocess.CompletedProcess[str]:
        if cmd[-1] == "--version":
            return _completed(0, stdout="pip-audit 2.10.0")
        if "-r" in cmd:
            return _completed(
                1,
                stderr="subprocess.CalledProcessError: ensurepip died with <Signals.SIGABRT: 6>",
            )
        if cmd[-1] == "--local":
            return _completed(1, stderr="vulnerability found")
        return _completed(1, stderr="unexpected command")

    monkeypatch.setattr(gatepack, "_run", fake_run)

    result = gatepack.gate_security_audit()

    assert result.passed is False
    assert "vulnerability found" in result.detail
