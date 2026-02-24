import asyncio
import json
import threading
import uuid
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict, Optional, Set
from urllib.parse import unquote, urlparse

from pydantic import ValidationError

from eap.environment import AsyncLocalExecutor
from eap.protocol import BatchedMacroRequest, StateManager
from eap.runtime.auth_scopes import (
    FULL_RUNTIME_SCOPES,
    SCOPE_POINTERS_READ,
    SCOPE_POINTERS_READ_ANY,
    SCOPE_RUNS_EXECUTE,
    SCOPE_RUNS_READ,
    SCOPE_RUNS_READ_ANY,
    SCOPE_RUNS_RESUME,
    SCOPE_RUNS_RESUME_ANY,
)


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

    def _parse_bearer_token(self) -> Optional[str]:
        auth_header = (self.headers.get("Authorization") or "").strip()
        if not auth_header.startswith("Bearer "):
            return None
        token = auth_header[len("Bearer ") :].strip()
        return token or None

    def _resolve_auth_context(self) -> Optional[Dict[str, Any]]:
        token = self._parse_bearer_token()
        scoped_policies = self.server.scoped_bearer_tokens
        required = self.server.required_bearer_token

        if not required and not scoped_policies:
            return {
                "actor_id": "anonymous",
                "scopes": set(FULL_RUNTIME_SCOPES),
                "auth_subject": "anonymous",
                "policy_profile": "trusted",
            }

        if not token:
            return None

        if token in scoped_policies:
            policy = scoped_policies[token]
            return {
                "actor_id": policy.get("actor_id"),
                "scopes": set(policy.get("scopes", set())),
                "auth_subject": policy.get("auth_subject"),
                "policy_profile": policy.get("policy_profile"),
                "template": policy.get("template"),
            }

        if required and token == required:
            return {
                "actor_id": "runtime-admin",
                "scopes": set(FULL_RUNTIME_SCOPES),
                "auth_subject": "required_bearer_token",
                "policy_profile": "trusted",
            }
        return None

    def _require_auth(self, required_scope: str) -> Optional[Dict[str, Any]]:
        context = self._resolve_auth_context()
        if context is None:
            self._send_error(401, "unauthorized", "Missing or invalid bearer token.")
            return None

        scopes: Set[str] = set(context.get("scopes", set()))
        if required_scope not in scopes and "*" not in scopes:
            self._send_error(
                403,
                "forbidden",
                f"Missing required scope '{required_scope}'.",
            )
            return None
        return context

    def _to_actor_metadata(self, auth_context: Dict[str, Any], operation: str) -> Dict[str, Any]:
        metadata: Dict[str, Any] = {
            "actor_id": auth_context.get("actor_id"),
            "owner_actor_id": auth_context.get("actor_id"),
            "actor_scopes": sorted(set(auth_context.get("scopes", set()))),
            "operation": operation,
            "auth_subject": auth_context.get("auth_subject"),
        }
        policy_profile = auth_context.get("policy_profile")
        if policy_profile:
            metadata["policy_profile"] = policy_profile
        policy_template = auth_context.get("template")
        if policy_template:
            metadata["policy_template"] = policy_template
        return metadata

    def _check_run_access(
        self,
        run_id: str,
        auth_context: Dict[str, Any],
        *,
        allow_any_scope: str,
    ) -> bool:
        actor_metadata = self.server.state_manager.get_run_actor_metadata(run_id=run_id)
        owner_actor_id = actor_metadata.get("owner_actor_id") or actor_metadata.get("actor_id")
        if not owner_actor_id:
            return True

        actor_id = auth_context.get("actor_id")
        scopes: Set[str] = set(auth_context.get("scopes", set()))
        if actor_id == owner_actor_id or allow_any_scope in scopes or "*" in scopes:
            return True
        self._send_error(
            403,
            "forbidden",
            f"Actor '{actor_id}' is not allowed to access run '{run_id}'.",
        )
        return False

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
        auth_context = self._require_auth(SCOPE_RUNS_EXECUTE)
        if auth_context is None:
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
            result = asyncio.run(
                self.server.executor.execute_macro(
                    macro,
                    actor_metadata=self._to_actor_metadata(auth_context, operation="execute"),
                )
            )
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
        auth_context = self._require_auth(SCOPE_RUNS_RESUME)
        if auth_context is None:
            return
        if not run_id:
            self._send_error(400, "validation_error", "run_id is required.")
            return
        if not self._check_run_access(
            run_id=run_id,
            auth_context=auth_context,
            allow_any_scope=SCOPE_RUNS_RESUME_ANY,
        ):
            return

        payload = self._read_json_body(required=False)
        if payload is None:
            return
        approvals = payload.get("approvals")
        if approvals is not None and not isinstance(approvals, dict):
            self._send_error(400, "validation_error", "Field 'approvals' must be a JSON object.")
            return

        try:
            result = asyncio.run(
                self.server.executor.resume_run(
                    run_id=run_id,
                    approvals=approvals,
                    actor_metadata=self._to_actor_metadata(auth_context, operation="resume"),
                )
            )
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
        auth_context = self._require_auth(SCOPE_RUNS_READ)
        if auth_context is None:
            return
        if not run_id:
            self._send_error(400, "validation_error", "run_id is required.")
            return
        if not self._check_run_access(
            run_id=run_id,
            auth_context=auth_context,
            allow_any_scope=SCOPE_RUNS_READ_ANY,
        ):
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
        actor_metadata = self.server.state_manager.get_run_actor_metadata(run_id=run_id)
        status = "failed" if summary.get("failed_steps", 0) > 0 else "succeeded"

        response_payload = {
            "request_id": _request_id(),
            "timestamp_utc": _timestamp_utc(),
            "run_id": run_id,
            "status": status,
            "summary": summary,
            "actor_metadata": actor_metadata,
            "trace_event_count": len(trace_events),
            "trace_events": trace_events,
        }
        self._send_json(200, response_payload)

    def _handle_get_pointer_summary(self, pointer_id: str) -> None:
        auth_context = self._require_auth(SCOPE_POINTERS_READ)
        if auth_context is None:
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

        pointer_metadata = pointer.get("metadata") if isinstance(pointer.get("metadata"), dict) else {}
        run_id = pointer_metadata.get("execution_run_id")
        if isinstance(run_id, str) and run_id:
            scopes: Set[str] = set(auth_context.get("scopes", set()))
            if SCOPE_POINTERS_READ_ANY not in scopes and "*" not in scopes:
                if not self._check_run_access(
                    run_id=run_id,
                    auth_context=auth_context,
                    allow_any_scope=SCOPE_RUNS_READ_ANY,
                ):
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
        scoped_bearer_tokens: Optional[Dict[str, Dict[str, Any]]],
    ):
        super().__init__(server_address, RequestHandlerClass)
        self.executor = executor
        self.state_manager = state_manager
        self.required_bearer_token = required_bearer_token
        self.scoped_bearer_tokens = scoped_bearer_tokens or {}


class EAPRuntimeHTTPServer:
    """Minimal HTTP runtime endpoints for external orchestrator integration."""

    @staticmethod
    def _normalize_scoped_bearer_tokens(
        scoped_bearer_tokens: Optional[Dict[str, Dict[str, Any]]],
    ) -> Dict[str, Dict[str, Any]]:
        normalized: Dict[str, Dict[str, Any]] = {}
        if not scoped_bearer_tokens:
            return normalized

        for raw_token, raw_policy in scoped_bearer_tokens.items():
            token = str(raw_token).strip()
            if not token or not isinstance(raw_policy, dict):
                continue
            actor_id = str(raw_policy.get("actor_id", "")).strip()
            auth_subject = str(raw_policy.get("auth_subject", "")).strip()

            scopes_value = raw_policy.get("scopes", [])
            if isinstance(scopes_value, str):
                scopes = [scope.strip() for scope in scopes_value.split(",") if scope.strip()]
            elif isinstance(scopes_value, list):
                scopes = [str(scope).strip() for scope in scopes_value if str(scope).strip()]
            else:
                scopes = []
            scopes = [scope for scope in scopes if scope in FULL_RUNTIME_SCOPES or scope == "*"]

            if not actor_id:
                continue
            if not scopes:
                continue
            normalized[token] = {
                "actor_id": actor_id,
                "auth_subject": auth_subject or f"scoped_token:{actor_id}",
                "scopes": sorted(set(scopes)),
            }
        return normalized

    def __init__(
        self,
        executor: AsyncLocalExecutor,
        state_manager: StateManager,
        host: str = "127.0.0.1",
        port: int = 0,
        required_bearer_token: Optional[str] = None,
        scoped_bearer_tokens: Optional[Dict[str, Dict[str, Any]]] = None,
    ):
        self._host = host
        normalized_scoped_tokens = self._normalize_scoped_bearer_tokens(scoped_bearer_tokens)
        self._httpd = _RuntimeHTTPServer(
            (host, port),
            _RuntimeRequestHandler,
            executor=executor,
            state_manager=state_manager,
            required_bearer_token=required_bearer_token,
            scoped_bearer_tokens=normalized_scoped_tokens,
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
