import asyncio
import json
import threading
import uuid
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict, Optional
from urllib.parse import unquote, urlparse

from pydantic import ValidationError

from eap.environment import AsyncLocalExecutor
from eap.protocol import BatchedMacroRequest, StateManager


def _timestamp_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _request_id() -> str:
    return f"req_{uuid.uuid4().hex[:12]}"


class _RuntimeRequestHandler(BaseHTTPRequestHandler):
    server: "_RuntimeHTTPServer"

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path == "/v1/eap/macro/execute":
            self._handle_execute_macro()
            return
        if parsed.path.startswith("/v1/eap/runs/") and parsed.path.endswith("/resume"):
            run_id = unquote(parsed.path[len("/v1/eap/runs/") : -len("/resume")]).strip()
            self._handle_resume_run(run_id=run_id)
            return
        self._send_error(404, "not_found", f"Path '{parsed.path}' is not registered.")

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path.startswith("/v1/eap/runs/"):
            run_id = unquote(parsed.path[len("/v1/eap/runs/") :]).strip()
            self._handle_get_run(run_id=run_id)
            return
        if parsed.path.startswith("/v1/eap/pointers/") and parsed.path.endswith("/summary"):
            pointer_id = unquote(parsed.path[len("/v1/eap/pointers/") : -len("/summary")]).strip()
            self._handle_get_pointer_summary(pointer_id=pointer_id)
            return
        self._send_error(404, "not_found", f"Path '{parsed.path}' is not registered.")

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A003
        # Keep test/runtime output quiet unless callers choose to add logging.
        return

    def _require_auth(self) -> bool:
        required = self.server.required_bearer_token
        if not required:
            return True

        auth_header = (self.headers.get("Authorization") or "").strip()
        if not auth_header.startswith("Bearer "):
            self._send_error(401, "unauthorized", "Missing or invalid bearer token.")
            return False

        token = auth_header[len("Bearer ") :].strip()
        if token != required:
            self._send_error(401, "unauthorized", "Missing or invalid bearer token.")
            return False
        return True

    def _read_json_body(self, required: bool = True) -> Optional[Dict[str, Any]]:
        content_length_header = self.headers.get("Content-Length")
        if not content_length_header:
            if required:
                self._send_error(400, "validation_error", "Request body is required.")
                return None
            return {}
        try:
            content_length = int(content_length_header)
        except ValueError:
            self._send_error(400, "validation_error", "Invalid Content-Length header.")
            return None
        if content_length <= 0:
            if required:
                self._send_error(400, "validation_error", "Request body is required.")
                return None
            return {}

        raw_body = self.rfile.read(content_length)
        try:
            payload = json.loads(raw_body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            self._send_error(400, "validation_error", "Request body must be valid JSON.")
            return None

        if not isinstance(payload, dict):
            self._send_error(400, "validation_error", "Request body must be a JSON object.")
            return None
        return payload

    def _handle_execute_macro(self) -> None:
        if not self._require_auth():
            return

        payload = self._read_json_body()
        if payload is None:
            return

        macro_payload = payload.get("macro")
        if macro_payload is None:
            self._send_error(400, "validation_error", "Field 'macro' is required.")
            return

        try:
            macro = BatchedMacroRequest.model_validate(macro_payload)
        except ValidationError as exc:
            self._send_error(
                400,
                "validation_error",
                "Invalid macro payload.",
                details={"errors": exc.errors()},
            )
            return

        try:
            result = asyncio.run(self.server.executor.execute_macro(macro))
        except Exception as exc:  # pragma: no cover - defensive safeguard
            self._send_error(
                500,
                "execution_error",
                f"Macro execution failed: {str(exc)}",
            )
            return

        if not result or "pointer_id" not in result:
            self._send_error(
                500,
                "execution_error",
                "Macro execution did not return a pointer response.",
            )
            return

        response_payload = {
            "request_id": _request_id(),
            "timestamp_utc": _timestamp_utc(),
            "pointer_id": result["pointer_id"],
            "summary": result.get("summary", ""),
            "metadata": result.get("metadata"),
        }
        self._send_json(200, response_payload)

    def _handle_resume_run(self, run_id: str) -> None:
        if not self._require_auth():
            return
        if not run_id:
            self._send_error(400, "validation_error", "run_id is required.")
            return

        payload = self._read_json_body(required=False)
        if payload is None:
            return
        approvals = payload.get("approvals")
        if approvals is not None and not isinstance(approvals, dict):
            self._send_error(400, "validation_error", "Field 'approvals' must be a JSON object.")
            return

        try:
            result = asyncio.run(self.server.executor.resume_run(run_id=run_id, approvals=approvals))
        except KeyError:
            self._send_error(404, "not_found", f"Execution checkpoint for run '{run_id}' not found.")
            return
        except ValueError as exc:
            self._send_error(400, "validation_error", str(exc))
            return
        except ValidationError as exc:
            self._send_error(
                400,
                "validation_error",
                "Invalid resume approval payload.",
                details={"errors": exc.errors()},
            )
            return
        except Exception as exc:  # pragma: no cover - defensive safeguard
            self._send_error(
                500,
                "execution_error",
                f"Run resume failed: {str(exc)}",
            )
            return

        if not result or "pointer_id" not in result:
            self._send_error(
                500,
                "execution_error",
                "Run resume did not return a pointer response.",
            )
            return

        response_payload = {
            "request_id": _request_id(),
            "timestamp_utc": _timestamp_utc(),
            "run_id": run_id,
            "pointer_id": result["pointer_id"],
            "summary": result.get("summary", ""),
            "metadata": result.get("metadata"),
        }
        self._send_json(200, response_payload)

    def _handle_get_run(self, run_id: str) -> None:
        if not self._require_auth():
            return
        if not run_id:
            self._send_error(400, "validation_error", "run_id is required.")
            return

        try:
            summary = self.server.state_manager.get_execution_summary(run_id)
        except KeyError:
            self._send_error(404, "not_found", f"Execution summary for run '{run_id}' not found.")
            return

        trace_events = [
            event.model_dump(mode="json")
            for event in self.server.state_manager.list_trace_events(run_id)
        ]
        status = "failed" if summary.get("failed_steps", 0) > 0 else "succeeded"

        response_payload = {
            "request_id": _request_id(),
            "timestamp_utc": _timestamp_utc(),
            "run_id": run_id,
            "status": status,
            "summary": summary,
            "trace_event_count": len(trace_events),
            "trace_events": trace_events,
        }
        self._send_json(200, response_payload)

    def _handle_get_pointer_summary(self, pointer_id: str) -> None:
        if not self._require_auth():
            return
        if not pointer_id:
            self._send_error(400, "validation_error", "pointer_id is required.")
            return

        pointer = next(
            (
                item
                for item in self.server.state_manager.list_pointers(include_expired=True)
                if item.get("pointer_id") == pointer_id
            ),
            None,
        )
        if pointer is None:
            self._send_error(404, "not_found", f"Pointer '{pointer_id}' not found.")
            return

        response_payload = {
            "request_id": _request_id(),
            "timestamp_utc": _timestamp_utc(),
            "pointer": {
                "pointer_id": pointer["pointer_id"],
                "summary": pointer.get("summary"),
                "metadata": pointer.get("metadata"),
                "created_at_utc": pointer.get("created_at_utc"),
                "ttl_seconds": pointer.get("ttl_seconds"),
                "expires_at_utc": pointer.get("expires_at_utc"),
                "is_expired": pointer.get("is_expired", False),
            },
        }
        self._send_json(200, response_payload)

    def _send_json(self, status_code: int, payload: Dict[str, Any]) -> None:
        encoded = json.dumps(payload, sort_keys=True).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def _send_error(
        self,
        status_code: int,
        error_type: str,
        message: str,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        payload: Dict[str, Any] = {
            "error_type": error_type,
            "message": message,
        }
        if details is not None:
            payload["details"] = details
        self._send_json(status_code, payload)


class _RuntimeHTTPServer(ThreadingHTTPServer):
    def __init__(
        self,
        server_address,
        RequestHandlerClass,  # noqa: N803
        executor: AsyncLocalExecutor,
        state_manager: StateManager,
        required_bearer_token: Optional[str],
    ):
        super().__init__(server_address, RequestHandlerClass)
        self.executor = executor
        self.state_manager = state_manager
        self.required_bearer_token = required_bearer_token


class EAPRuntimeHTTPServer:
    """Minimal HTTP runtime endpoints for external orchestrator integration."""

    def __init__(
        self,
        executor: AsyncLocalExecutor,
        state_manager: StateManager,
        host: str = "127.0.0.1",
        port: int = 0,
        required_bearer_token: Optional[str] = None,
    ):
        self._host = host
        self._httpd = _RuntimeHTTPServer(
            (host, port),
            _RuntimeRequestHandler,
            executor=executor,
            state_manager=state_manager,
            required_bearer_token=required_bearer_token,
        )
        self._thread: Optional[threading.Thread] = None

    @property
    def host(self) -> str:
        return self._host

    @property
    def port(self) -> int:
        return int(self._httpd.server_address[1])

    @property
    def base_url(self) -> str:
        return f"http://{self.host}:{self.port}"

    def start(self) -> "EAPRuntimeHTTPServer":
        if self._thread and self._thread.is_alive():
            return self
        self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)
        self._thread.start()
        return self

    def stop(self) -> None:
        self._httpd.shutdown()
        self._httpd.server_close()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)

    def __enter__(self) -> "EAPRuntimeHTTPServer":
        return self.start()

    def __exit__(self, exc_type, exc, tb) -> None:
        self.stop()
