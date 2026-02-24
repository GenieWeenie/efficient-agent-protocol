import json
import os
from dataclasses import dataclass
from typing import Dict, Optional


DEFAULT_BASE_URL = "http://localhost:1234"
DEFAULT_MODEL = "nemotron-orchestrator-8b"
DEFAULT_TIMEOUT_SECONDS = 60
DEFAULT_TEMPERATURE = 0.0
DEFAULT_EXECUTOR_MAX_CONCURRENCY = 8


@dataclass(frozen=True)
class LLMClientSettings:
    base_url: str
    model_name: str
    api_key: str
    timeout_seconds: int
    temperature: float
    extra_headers: Dict[str, str]


@dataclass(frozen=True)
class ToolLimitSettings:
    max_concurrency: Optional[int] = None
    requests_per_second: Optional[float] = None
    burst_capacity: Optional[int] = None


@dataclass(frozen=True)
class ExecutorLimitSettings:
    max_global_concurrency: int
    global_requests_per_second: Optional[float]
    global_burst_capacity: Optional[int]
    per_tool_limits: Dict[str, ToolLimitSettings]


@dataclass(frozen=True)
class EAPSettings:
    architect: LLMClientSettings
    auditor: LLMClientSettings
    executor: ExecutorLimitSettings


def _parse_float(value: str, field_name: str) -> float:
    try:
        return float(value)
    except ValueError as exc:
        raise ValueError(f"Invalid float for {field_name}: {value}") from exc


def _parse_int(value: str, field_name: str) -> int:
    try:
        return int(value)
    except ValueError as exc:
        raise ValueError(f"Invalid integer for {field_name}: {value}") from exc


def _validate_base_url(base_url: str, field_name: str) -> str:
    normalized = base_url.rstrip("/")
    if not normalized.startswith(("http://", "https://")):
        raise ValueError(f"{field_name} must start with http:// or https://")
    return normalized


def _parse_optional_float(value: str, field_name: str) -> Optional[float]:
    normalized = value.strip()
    if not normalized:
        return None
    parsed = _parse_float(normalized, field_name)
    return parsed


def _parse_optional_int(value: str, field_name: str) -> Optional[int]:
    normalized = value.strip()
    if not normalized:
        return None
    parsed = _parse_int(normalized, field_name)
    return parsed


def _parse_extra_headers(value: str, field_name: str) -> Dict[str, str]:
    normalized = value.strip() or "{}"
    try:
        parsed = json.loads(normalized)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{field_name} must be valid JSON.") from exc

    if not isinstance(parsed, dict):
        raise ValueError(f"{field_name} must be a JSON object.")

    headers: Dict[str, str] = {}
    for raw_key, raw_value in parsed.items():
        if not isinstance(raw_key, str) or not raw_key.strip():
            raise ValueError(f"{field_name} keys must be non-empty strings.")
        if not isinstance(raw_value, str) or not raw_value.strip():
            raise ValueError(f"{field_name} values must be non-empty strings.")
        headers[raw_key.strip()] = raw_value.strip()
    return headers


def _build_client_settings(role_prefix: str) -> LLMClientSettings:
    base_url = _validate_base_url(
        os.getenv(f"{role_prefix}_BASE_URL", os.getenv("EAP_BASE_URL", DEFAULT_BASE_URL)),
        f"{role_prefix}_BASE_URL",
    )

    model_name = os.getenv(f"{role_prefix}_MODEL", os.getenv("EAP_MODEL", DEFAULT_MODEL)).strip()
    if not model_name:
        raise ValueError(f"{role_prefix}_MODEL cannot be empty")

    api_key = os.getenv(f"{role_prefix}_API_KEY", os.getenv("EAP_API_KEY", "not-needed")).strip()
    if not api_key:
        raise ValueError(f"{role_prefix}_API_KEY cannot be empty")

    timeout_raw = os.getenv(f"{role_prefix}_TIMEOUT_SECONDS", os.getenv("EAP_TIMEOUT_SECONDS", str(DEFAULT_TIMEOUT_SECONDS)))
    timeout_seconds = _parse_int(timeout_raw, f"{role_prefix}_TIMEOUT_SECONDS")
    if timeout_seconds <= 0:
        raise ValueError(f"{role_prefix}_TIMEOUT_SECONDS must be > 0")

    temperature_raw = os.getenv(f"{role_prefix}_TEMPERATURE", os.getenv("EAP_TEMPERATURE", str(DEFAULT_TEMPERATURE)))
    temperature = _parse_float(temperature_raw, f"{role_prefix}_TEMPERATURE")
    if temperature < 0:
        raise ValueError(f"{role_prefix}_TEMPERATURE must be >= 0")

    global_extra_headers = _parse_extra_headers(
        os.getenv("EAP_EXTRA_HEADERS_JSON", "{}"),
        "EAP_EXTRA_HEADERS_JSON",
    )
    role_extra_headers = _parse_extra_headers(
        os.getenv(f"{role_prefix}_EXTRA_HEADERS_JSON", "{}"),
        f"{role_prefix}_EXTRA_HEADERS_JSON",
    )
    extra_headers = dict(global_extra_headers)
    extra_headers.update(role_extra_headers)

    return LLMClientSettings(
        base_url=base_url,
        model_name=model_name,
        api_key=api_key,
        timeout_seconds=timeout_seconds,
        temperature=temperature,
        extra_headers=extra_headers,
    )


def _validate_tool_limit_settings(tool_name: str, limits: ToolLimitSettings) -> None:
    if not tool_name.strip():
        raise ValueError("Per-tool limit keys must be non-empty tool names.")
    if limits.max_concurrency is not None and (
        not isinstance(limits.max_concurrency, int) or isinstance(limits.max_concurrency, bool)
    ):
        raise ValueError(f"Per-tool max_concurrency for '{tool_name}' must be an integer.")
    if limits.max_concurrency is not None and limits.max_concurrency <= 0:
        raise ValueError(f"Per-tool max_concurrency for '{tool_name}' must be > 0")
    if limits.requests_per_second is not None and (
        not isinstance(limits.requests_per_second, (int, float)) or isinstance(limits.requests_per_second, bool)
    ):
        raise ValueError(f"Per-tool requests_per_second for '{tool_name}' must be numeric.")
    if limits.requests_per_second is not None and limits.requests_per_second <= 0:
        raise ValueError(f"Per-tool requests_per_second for '{tool_name}' must be > 0")
    if limits.burst_capacity is not None and (
        not isinstance(limits.burst_capacity, int) or isinstance(limits.burst_capacity, bool)
    ):
        raise ValueError(f"Per-tool burst_capacity for '{tool_name}' must be an integer.")
    if limits.burst_capacity is not None and limits.burst_capacity <= 0:
        raise ValueError(f"Per-tool burst_capacity for '{tool_name}' must be > 0")
    if limits.burst_capacity is not None and limits.requests_per_second is None:
        raise ValueError(
            f"Per-tool burst_capacity for '{tool_name}' requires requests_per_second"
        )


def _build_executor_limits() -> ExecutorLimitSettings:
    max_concurrency = _parse_int(
        os.getenv("EAP_EXECUTOR_MAX_CONCURRENCY", str(DEFAULT_EXECUTOR_MAX_CONCURRENCY)),
        "EAP_EXECUTOR_MAX_CONCURRENCY",
    )
    if max_concurrency <= 0:
        raise ValueError("EAP_EXECUTOR_MAX_CONCURRENCY must be > 0")

    global_rps = _parse_optional_float(
        os.getenv("EAP_EXECUTOR_GLOBAL_RPS", ""),
        "EAP_EXECUTOR_GLOBAL_RPS",
    )
    if global_rps is not None and global_rps <= 0:
        raise ValueError("EAP_EXECUTOR_GLOBAL_RPS must be > 0")

    global_burst = _parse_optional_int(
        os.getenv("EAP_EXECUTOR_GLOBAL_BURST", ""),
        "EAP_EXECUTOR_GLOBAL_BURST",
    )
    if global_burst is not None and global_burst <= 0:
        raise ValueError("EAP_EXECUTOR_GLOBAL_BURST must be > 0")
    if global_burst is not None and global_rps is None:
        raise ValueError("EAP_EXECUTOR_GLOBAL_BURST requires EAP_EXECUTOR_GLOBAL_RPS")

    per_tool_raw = os.getenv("EAP_EXECUTOR_PER_TOOL_LIMITS_JSON", "{}").strip() or "{}"
    try:
        parsed = json.loads(per_tool_raw)
    except json.JSONDecodeError as exc:
        raise ValueError("EAP_EXECUTOR_PER_TOOL_LIMITS_JSON must be valid JSON.") from exc
    if not isinstance(parsed, dict):
        raise ValueError("EAP_EXECUTOR_PER_TOOL_LIMITS_JSON must be a JSON object.")

    per_tool_limits: Dict[str, ToolLimitSettings] = {}
    for tool_name, raw_limits in parsed.items():
        if not isinstance(raw_limits, dict):
            raise ValueError(f"Per-tool limit for '{tool_name}' must be a JSON object.")

        limit_settings = ToolLimitSettings(
            max_concurrency=raw_limits.get("max_concurrency"),
            requests_per_second=raw_limits.get("requests_per_second"),
            burst_capacity=raw_limits.get("burst_capacity"),
        )
        _validate_tool_limit_settings(tool_name, limit_settings)
        per_tool_limits[tool_name] = limit_settings

    return ExecutorLimitSettings(
        max_global_concurrency=max_concurrency,
        global_requests_per_second=global_rps,
        global_burst_capacity=global_burst,
        per_tool_limits=per_tool_limits,
    )


def load_settings() -> EAPSettings:
    return EAPSettings(
        architect=_build_client_settings("EAP_ARCHITECT"),
        auditor=_build_client_settings("EAP_AUDITOR"),
        executor=_build_executor_limits(),
    )
