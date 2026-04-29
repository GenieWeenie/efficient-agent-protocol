from __future__ import annotations

import asyncio
import json
import threading
import time
import types
import uuid
from datetime import datetime, timezone
from typing import Awaitable, Callable, Optional, Protocol, Set, Type
from urllib.parse import unquote

import uvicorn
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
from eap.runtime.guardrails import (
    RUNTIME_OPERATION_MACRO_EXECUTE,
    RUNTIME_OPERATION_POINTER_SUMMARY,
    RUNTIME_OPERATION_RUN_READ,
    RUNTIME_OPERATION_RUN_RESUME,
    ConcurrencyToken,
    RuntimeGuardrails,
    normalize_concurrency_limits,
    normalize_rate_limit_rules,
)

AuthContext = dict[str, object]
ScopedTokenPolicy = dict[str, object]
JsonPayload = dict[str, object]
ASGIScope = dict[str, object]
ASGIMessage = dict[str, object]
class ASGIReceive(Protocol):
    def __call__(self) -> Awaitable[ASGIMessage]:
        ...


class ASGISend(Protocol):
    def __call__(self, message: ASGIMessage) -> Awaitable[None]:
        ...

DEFAULT_MAX_REQUEST_BODY_BYTES = 1_000_000


def _timestamp_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _request_id() -> str:
    return f"req_{uuid.uuid4().hex[:12]}"


def _scopes_from_context(ctx: AuthContext) -> Set[str]:
    raw = ctx.get("scopes")
    if isinstance(raw, (set, frozenset)):
        return {str(scope) for scope in raw}
    if isinstance(raw, list):
        return {str(scope) for scope in raw}
    return set()


def _str_field(ctx: dict[str, object], key: str, default: str = "") -> str:
    val = ctx.get(key)
    return str(val) if val is not None else default


class _HTTPResponse(Exception):
    def __init__(
        self,
        status_code: int,
        payload: JsonPayload,
        headers: Optional[dict[str, str]] = None,
    ) -> None:
        super().__init__(str(status_code))
        self.status_code = status_code
        self.payload = payload
        self.headers = headers or {}


class _RuntimeState:
    def __init__(
        self,
        executor: AsyncLocalExecutor,
        state_manager: StateManager,
        required_bearer_token: Optional[str],
        scoped_bearer_tokens: dict[str, ScopedTokenPolicy],
        guardrails: RuntimeGuardrails,
    ) -> None:
        self.executor = executor
        self.state_manager = state_manager
        self.required_bearer_token = required_bearer_token
        self.scoped_bearer_tokens = scoped_bearer_tokens
        self.guardrails = guardrails
        self._guardrail_lock = threading.Lock()
        self.guardrail_counters: dict[str, int] = {"rate_limited": 0, "throttled": 0}

    def record_guardrail_event(self, event_type: str, details: JsonPayload) -> None:
        with self._guardrail_lock:
            self.guardrail_counters[event_type] = self.guardrail_counters.get(event_type, 0) + 1
        log_payload: JsonPayload = {
            "event_type": event_type,
            "details": details,
            "counters": dict(self.guardrail_counters),
            "timestamp_utc": _timestamp_utc(),
        }
        print(f"[runtime:guardrail] {json.dumps(log_payload, sort_keys=True)}")


class _RuntimeASGIApp:
    def __init__(self, state: _RuntimeState, max_request_body_bytes: int) -> None:
        self._state = state
        self._max_request_body_bytes = max_request_body_bytes

    async def __call__(self, scope: ASGIScope, receive: ASGIReceive, send: ASGISend) -> None:
        if scope.get("type") != "http":
            await self._send_error(send, 500, "server_error", "Unsupported ASGI scope type.")
            return

        method = str(scope.get("method", "")).upper()
        path = unquote(str(scope.get("path", ""))).split("?", 1)[0]
        headers = self._headers_from_scope(scope)

        try:
            payload = await self._dispatch(method=method, path=path, headers=headers, receive=receive)
        except _HTTPResponse as response:
            await self._send_json(send, response.status_code, response.payload, headers=response.headers)
            return
        except Exception as exc:  # pragma: no cover - defensive ASGI boundary
            await self._send_error(send, 500, "server_error", f"Runtime request failed: {str(exc)}")
            return

        await self._send_json(send, 200, payload)

    async def _dispatch(
        self,
        *,
        method: str,
        path: str,
        headers: dict[str, str],
        receive: ASGIReceive,
    ) -> JsonPayload:
        if method == "POST" and path == "/v1/eap/macro/execute":
            return await self._handle_execute_macro(headers=headers, receive=receive)
        if method == "POST" and path.startswith("/v1/eap/runs/") and path.endswith("/resume"):
            run_id = path[len("/v1/eap/runs/"):-len("/resume")].strip()
            return await self._handle_resume_run(run_id=run_id, headers=headers, receive=receive)
        if method == "GET" and path.startswith("/v1/eap/runs/"):
            run_id = path[len("/v1/eap/runs/"):].strip()
            return self._handle_get_run(run_id=run_id, headers=headers)
        if method == "GET" and path.startswith("/v1/eap/pointers/") and path.endswith("/summary"):
            pointer_id = path[len("/v1/eap/pointers/"):-len("/summary")].strip()
            return self._handle_get_pointer_summary(pointer_id=pointer_id, headers=headers)
        raise self._error(404, "not_found", f"Path '{path}' is not registered.")

    def _headers_from_scope(self, scope: ASGIScope) -> dict[str, str]:
        normalized: dict[str, str] = {}
        raw_headers = scope.get("headers", [])
        if not isinstance(raw_headers, list):
            return normalized
        for item in raw_headers:
            if not isinstance(item, tuple) or len(item) != 2:
                continue
            raw_name, raw_value = item
            if not isinstance(raw_name, bytes) or not isinstance(raw_value, bytes):
                continue
            normalized[raw_name.decode("latin-1").lower()] = raw_value.decode("latin-1")
        return normalized

    def _parse_bearer_token(self, headers: dict[str, str]) -> Optional[str]:
        auth_header = headers.get("authorization", "").strip()
        if not auth_header.startswith("Bearer "):
            return None
        token = auth_header[len("Bearer "):].strip()
        return token or None

    def _resolve_auth_context(self, headers: dict[str, str]) -> Optional[AuthContext]:
        token = self._parse_bearer_token(headers)
        scoped_policies = self._state.scoped_bearer_tokens
        required = self._state.required_bearer_token

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
            raw_scopes = policy.get("scopes")
            scopes: Set[str]
            if isinstance(raw_scopes, (set, frozenset)):
                scopes = {str(scope) for scope in raw_scopes}
            elif isinstance(raw_scopes, list):
                scopes = {str(scope) for scope in raw_scopes}
            else:
                scopes = set()
            return {
                "actor_id": policy.get("actor_id"),
                "scopes": scopes,
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

    def _require_auth(self, headers: dict[str, str], required_scope: str) -> AuthContext:
        context = self._resolve_auth_context(headers)
        if context is None:
            raise self._error(401, "unauthorized", "Missing or invalid bearer token.")

        scopes = _scopes_from_context(context)
        if required_scope not in scopes and "*" not in scopes:
            raise self._error(403, "forbidden", f"Missing required scope '{required_scope}'.")
        return context

    def _enforce_rate_limit(self, *, operation: str, auth_context: AuthContext) -> None:
        actor_id = _str_field(auth_context, "actor_id") or _str_field(auth_context, "auth_subject") or "anonymous"
        actor_id = actor_id.strip() or "anonymous"
        decision = self._state.guardrails.check_rate_limit(operation=operation, actor_id=actor_id)
        if decision.allowed:
            return

        details: JsonPayload = {
            "operation": operation,
            "actor_id": actor_id,
            "limit": decision.limit,
            "window_seconds": decision.window_seconds,
            "retry_after_seconds": round(decision.retry_after_seconds, 3),
        }
        self._state.record_guardrail_event("rate_limited", details)
        raise self._error(
            429,
            "rate_limited",
            f"Rate limit exceeded for '{operation}'.",
            details=details,
            headers={"Retry-After": RuntimeGuardrails.retry_after_header_value(decision.retry_after_seconds)},
        )

    def _acquire_concurrency(self, *, operation: str, run_id: Optional[str] = None) -> ConcurrencyToken:
        decision, token = self._state.guardrails.acquire_concurrency(operation=operation, run_id=run_id)
        if decision.allowed and token is not None:
            return token

        details: JsonPayload = {
            "operation": operation,
            "limit_type": decision.limit_type,
            "limit": decision.limit,
            "current_inflight": decision.current_inflight,
        }
        if run_id:
            details["run_id"] = run_id
        self._state.record_guardrail_event("throttled", details)
        raise self._error(
            429,
            "throttled",
            f"Concurrency limit exceeded for '{operation}'.",
            details=details,
        )

    def _to_actor_metadata(self, auth_context: AuthContext, operation: str) -> JsonPayload:
        scopes = _scopes_from_context(auth_context)
        metadata: JsonPayload = {
            "actor_id": auth_context.get("actor_id"),
            "owner_actor_id": auth_context.get("actor_id"),
            "actor_scopes": sorted(scopes),
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

    def _check_run_access(self, run_id: str, auth_context: AuthContext, *, allow_any_scope: str) -> None:
        actor_metadata = self._state.state_manager.get_run_actor_metadata(run_id=run_id)
        owner_actor_id = actor_metadata.get("owner_actor_id") or actor_metadata.get("actor_id")
        if not owner_actor_id:
            return

        actor_id = auth_context.get("actor_id")
        scopes = _scopes_from_context(auth_context)
        if actor_id == owner_actor_id or allow_any_scope in scopes or "*" in scopes:
            return
        raise self._error(403, "forbidden", f"Actor '{actor_id}' is not allowed to access run '{run_id}'.")

    async def _read_json_body(self, receive: ASGIReceive, *, required: bool = True) -> JsonPayload:
        chunks: list[bytes] = []
        total_bytes = 0
        more_body = True
        while more_body:
            raw_message = await receive()
            if not isinstance(raw_message, dict):
                raise self._error(400, "validation_error", "Invalid ASGI request body message.")
            body = raw_message.get("body", b"")
            if not isinstance(body, bytes):
                raise self._error(400, "validation_error", "Invalid request body chunk.")
            total_bytes += len(body)
            if total_bytes > self._max_request_body_bytes:
                raise self._error(
                    413,
                    "request_body_too_large",
                    f"Request body exceeds {self._max_request_body_bytes} bytes.",
                    details={"max_request_body_bytes": self._max_request_body_bytes},
                )
            if body:
                chunks.append(body)
            more_body = bool(raw_message.get("more_body", False))

        raw_body = b"".join(chunks)
        if not raw_body:
            if required:
                raise self._error(400, "validation_error", "Request body is required.")
            return {}

        try:
            payload = json.loads(raw_body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise self._error(400, "validation_error", "Request body must be valid JSON.")

        if not isinstance(payload, dict):
            raise self._error(400, "validation_error", "Request body must be a JSON object.")
        return payload

    async def _handle_execute_macro(self, *, headers: dict[str, str], receive: ASGIReceive) -> JsonPayload:
        auth_context = self._require_auth(headers, SCOPE_RUNS_EXECUTE)
        self._enforce_rate_limit(operation=RUNTIME_OPERATION_MACRO_EXECUTE, auth_context=auth_context)
        payload = await self._read_json_body(receive)

        macro_payload = payload.get("macro")
        if macro_payload is None:
            raise self._error(400, "validation_error", "Field 'macro' is required.")

        try:
            macro = BatchedMacroRequest.model_validate(macro_payload)
        except ValidationError as exc:
            raise self._error(400, "validation_error", "Invalid macro payload.", details={"errors": exc.errors()})

        concurrency_token = self._acquire_concurrency(operation=RUNTIME_OPERATION_MACRO_EXECUTE)
        try:
            try:
                result = await self._state.executor.execute_macro(
                    macro,
                    actor_metadata=self._to_actor_metadata(auth_context, operation="execute"),
                )
            except Exception as exc:  # pragma: no cover - defensive safeguard
                raise self._error(500, "execution_error", f"Macro execution failed: {str(exc)}")
        finally:
            self._state.guardrails.release_concurrency(concurrency_token)

        if not result or "pointer_id" not in result:
            raise self._error(500, "execution_error", "Macro execution did not return a pointer response.")

        return {
            "request_id": _request_id(),
            "timestamp_utc": _timestamp_utc(),
            "pointer_id": result["pointer_id"],
            "summary": result.get("summary", ""),
            "metadata": result.get("metadata"),
        }

    async def _handle_resume_run(
        self,
        *,
        run_id: str,
        headers: dict[str, str],
        receive: ASGIReceive,
    ) -> JsonPayload:
        auth_context = self._require_auth(headers, SCOPE_RUNS_RESUME)
        self._enforce_rate_limit(operation=RUNTIME_OPERATION_RUN_RESUME, auth_context=auth_context)
        if not run_id:
            raise self._error(400, "validation_error", "run_id is required.")
        self._check_run_access(run_id=run_id, auth_context=auth_context, allow_any_scope=SCOPE_RUNS_RESUME_ANY)

        payload = await self._read_json_body(receive, required=False)
        approvals = payload.get("approvals")
        if approvals is not None and not isinstance(approvals, dict):
            raise self._error(400, "validation_error", "Field 'approvals' must be a JSON object.")

        concurrency_token = self._acquire_concurrency(operation=RUNTIME_OPERATION_RUN_RESUME, run_id=run_id)
        try:
            try:
                result = await self._state.executor.resume_run(
                    run_id=run_id,
                    approvals=approvals,
                    actor_metadata=self._to_actor_metadata(auth_context, operation="resume"),
                )
            except KeyError:
                raise self._error(404, "not_found", f"Execution checkpoint for run '{run_id}' not found.")
            except ValueError as exc:
                raise self._error(400, "validation_error", str(exc))
            except ValidationError as exc:
                raise self._error(
                    400,
                    "validation_error",
                    "Invalid resume approval payload.",
                    details={"errors": exc.errors()},
                )
            except Exception as exc:  # pragma: no cover - defensive safeguard
                raise self._error(500, "execution_error", f"Run resume failed: {str(exc)}")
        finally:
            self._state.guardrails.release_concurrency(concurrency_token)

        if not result or "pointer_id" not in result:
            raise self._error(500, "execution_error", "Run resume did not return a pointer response.")

        return {
            "request_id": _request_id(),
            "timestamp_utc": _timestamp_utc(),
            "run_id": run_id,
            "pointer_id": result["pointer_id"],
            "summary": result.get("summary", ""),
            "metadata": result.get("metadata"),
        }

    def _handle_get_run(self, *, run_id: str, headers: dict[str, str]) -> JsonPayload:
        auth_context = self._require_auth(headers, SCOPE_RUNS_READ)
        self._enforce_rate_limit(operation=RUNTIME_OPERATION_RUN_READ, auth_context=auth_context)
        if not run_id:
            raise self._error(400, "validation_error", "run_id is required.")
        self._check_run_access(run_id=run_id, auth_context=auth_context, allow_any_scope=SCOPE_RUNS_READ_ANY)

        try:
            summary = self._state.state_manager.get_execution_summary(run_id)
        except KeyError:
            raise self._error(404, "not_found", f"Execution summary for run '{run_id}' not found.")

        trace_events: list[dict[str, object]] = [
            event.model_dump(mode="json")
            for event in self._state.state_manager.list_trace_events(run_id)
        ]
        actor_metadata = self._state.state_manager.get_run_actor_metadata(run_id=run_id)
        status = "failed" if summary.get("failed_steps", 0) > 0 else "succeeded"

        return {
            "request_id": _request_id(),
            "timestamp_utc": _timestamp_utc(),
            "run_id": run_id,
            "status": status,
            "summary": summary,
            "actor_metadata": actor_metadata,
            "trace_event_count": len(trace_events),
            "trace_events": trace_events,
        }

    def _handle_get_pointer_summary(self, *, pointer_id: str, headers: dict[str, str]) -> JsonPayload:
        auth_context = self._require_auth(headers, SCOPE_POINTERS_READ)
        self._enforce_rate_limit(operation=RUNTIME_OPERATION_POINTER_SUMMARY, auth_context=auth_context)
        if not pointer_id:
            raise self._error(400, "validation_error", "pointer_id is required.")

        pointer: Optional[dict[str, object]] = next(
            (
                item
                for item in self._state.state_manager.list_pointers(include_expired=True)
                if item.get("pointer_id") == pointer_id
            ),
            None,
        )
        if pointer is None:
            raise self._error(404, "not_found", f"Pointer '{pointer_id}' not found.")

        raw_metadata = pointer.get("metadata")
        pointer_metadata: dict[str, object] = raw_metadata if isinstance(raw_metadata, dict) else {}
        run_id = pointer_metadata.get("execution_run_id")
        if isinstance(run_id, str) and run_id:
            scopes = _scopes_from_context(auth_context)
            if SCOPE_POINTERS_READ_ANY not in scopes and "*" not in scopes:
                self._check_run_access(
                    run_id=run_id,
                    auth_context=auth_context,
                    allow_any_scope=SCOPE_RUNS_READ_ANY,
                )

        return {
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

    def _error(
        self,
        status_code: int,
        error_type: str,
        message: str,
        details: Optional[JsonPayload] = None,
        headers: Optional[dict[str, str]] = None,
    ) -> _HTTPResponse:
        payload: JsonPayload = {"error_type": error_type, "message": message}
        if details is not None:
            payload["details"] = details
        return _HTTPResponse(status_code, payload, headers=headers)

    async def _send_error(
        self,
        send: ASGISend,
        status_code: int,
        error_type: str,
        message: str,
        details: Optional[JsonPayload] = None,
        headers: Optional[dict[str, str]] = None,
    ) -> None:
        await self._send_json(send, status_code, self._error(status_code, error_type, message, details).payload, headers)

    async def _send_json(
        self,
        send: ASGISend,
        status_code: int,
        payload: JsonPayload,
        headers: Optional[dict[str, str]] = None,
    ) -> None:
        encoded = json.dumps(payload, sort_keys=True).encode("utf-8")
        response_headers = [
            (b"content-type", b"application/json"),
            (b"content-length", str(len(encoded)).encode("ascii")),
        ]
        if headers:
            for key, value in headers.items():
                response_headers.append((key.lower().encode("latin-1"), value.encode("latin-1")))
        await send({"type": "http.response.start", "status": status_code, "headers": response_headers})
        await send({"type": "http.response.body", "body": encoded})


class EAPRuntimeHTTPServer:
    """ASGI-backed runtime endpoints for external orchestrator integration."""

    @staticmethod
    def _normalize_scoped_bearer_tokens(
        scoped_bearer_tokens: Optional[dict[str, dict[str, object]]],
    ) -> dict[str, ScopedTokenPolicy]:
        normalized: dict[str, ScopedTokenPolicy] = {}
        if not scoped_bearer_tokens:
            return normalized

        for raw_token, raw_policy in scoped_bearer_tokens.items():
            token = str(raw_token).strip()
            if not token or not isinstance(raw_policy, dict):
                continue
            actor_id = str(raw_policy.get("actor_id", "")).strip()
            auth_subject = str(raw_policy.get("auth_subject", "")).strip()
            policy_profile = str(raw_policy.get("policy_profile", "")).strip()
            template = str(raw_policy.get("template", "")).strip()

            scopes_value = raw_policy.get("scopes", [])
            scopes: list[str]
            if isinstance(scopes_value, str):
                scopes = [scope.strip() for scope in scopes_value.split(",") if scope.strip()]
            elif isinstance(scopes_value, list):
                scopes = [str(scope).strip() for scope in scopes_value if str(scope).strip()]
            else:
                scopes = []
            scopes = [scope for scope in scopes if scope in FULL_RUNTIME_SCOPES or scope == "*"]

            if not actor_id or not scopes:
                continue
            entry: ScopedTokenPolicy = {
                "actor_id": actor_id,
                "auth_subject": auth_subject or f"scoped_token:{actor_id}",
                "scopes": sorted(set(scopes)),
            }
            if policy_profile:
                entry["policy_profile"] = policy_profile
            if template:
                entry["template"] = template
            normalized[token] = entry
        return normalized

    def __init__(
        self,
        executor: AsyncLocalExecutor,
        state_manager: StateManager,
        host: str = "127.0.0.1",
        port: int = 0,
        required_bearer_token: Optional[str] = None,
        scoped_bearer_tokens: Optional[dict[str, dict[str, object]]] = None,
        rate_limit_rules: Optional[dict[str, dict[str, object]]] = None,
        concurrency_limits: Optional[dict[str, object]] = None,
        max_request_body_bytes: int = DEFAULT_MAX_REQUEST_BODY_BYTES,
    ) -> None:
        if port < 0 or port > 65535:
            raise ValueError("port must be between 0 and 65535")
        if max_request_body_bytes <= 0:
            raise ValueError("max_request_body_bytes must be greater than 0")

        self._host = host
        self._configured_port = port
        self._bound_port: Optional[int] = None
        normalized_scoped_tokens = self._normalize_scoped_bearer_tokens(scoped_bearer_tokens)
        normalized_rate_limits = normalize_rate_limit_rules(rate_limit_rules)
        normalized_concurrency_limits = normalize_concurrency_limits(concurrency_limits)
        self._state = _RuntimeState(
            executor=executor,
            state_manager=state_manager,
            required_bearer_token=required_bearer_token,
            scoped_bearer_tokens=normalized_scoped_tokens,
            guardrails=RuntimeGuardrails(
                rate_limit_rules=normalized_rate_limits,
                concurrency_limits=normalized_concurrency_limits,
            ),
        )
        self._app = _RuntimeASGIApp(self._state, max_request_body_bytes=max_request_body_bytes)
        self._config = uvicorn.Config(
            self._app,
            host=host,
            port=port,
            log_level="warning",
            access_log=False,
            lifespan="off",
        )
        self._server = uvicorn.Server(self._config)
        self._thread: Optional[threading.Thread] = None

    @property
    def host(self) -> str:
        return self._host

    @property
    def port(self) -> int:
        if self._bound_port is not None:
            return self._bound_port
        return self._configured_port

    @property
    def base_url(self) -> str:
        return f"http://{self.host}:{self.port}"

    def start(self) -> EAPRuntimeHTTPServer:
        if self._thread and self._thread.is_alive():
            return self
        self._server.should_exit = False
        self._thread = threading.Thread(target=self._server.run, daemon=True)
        self._thread.start()
        self._wait_until_started()
        return self

    def _wait_until_started(self) -> None:
        deadline = time.monotonic() + 5.0
        while not self._server.started:
            if not self._thread or not self._thread.is_alive():
                raise RuntimeError("EAP runtime ASGI server failed to start.")
            if time.monotonic() > deadline:
                raise TimeoutError("Timed out waiting for EAP runtime ASGI server to start.")
            threading.Event().wait(0.01)
        self._bound_port = self._resolve_bound_port()

    def _resolve_bound_port(self) -> int:
        for server in self._server.servers:
            sockets = getattr(server, "sockets", [])
            for sock in sockets:
                address = sock.getsockname()
                if isinstance(address, tuple) and len(address) >= 2:
                    return int(address[1])
        return self._configured_port

    def stop(self) -> None:
        self._server.should_exit = True
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)
        self._thread = None

    def __enter__(self) -> EAPRuntimeHTTPServer:
        return self.start()

    def __exit__(
        self,
        exc_type: Optional[Type[BaseException]],
        exc: Optional[BaseException],
        tb: Optional[types.TracebackType],
    ) -> None:
        self.stop()
