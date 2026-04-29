from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
HTTP_API_PATH = REPO_ROOT / "eap" / "runtime" / "http_api.py"


def test_runtime_http_api_uses_asgi_server_boundary() -> None:
    source = HTTP_API_PATH.read_text(encoding="utf-8")

    assert "uvicorn.Server" in source
    assert "ThreadingHTTPServer" not in source
    assert "BaseHTTPRequestHandler" not in source
    assert "asyncio.run(" not in source


def test_runtime_http_api_enforces_request_body_cap() -> None:
    source = HTTP_API_PATH.read_text(encoding="utf-8")

    assert "DEFAULT_MAX_REQUEST_BODY_BYTES" in source
    assert "request_body_too_large" in source
    assert "max_request_body_bytes" in source
