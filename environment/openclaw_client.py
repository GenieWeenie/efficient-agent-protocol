import json
from dataclasses import dataclass
from typing import Any, Dict, Optional

import requests


@dataclass(frozen=True)
class OpenClawToolInvokeRequest:
    name: str
    arguments: Dict[str, Any]


@dataclass(frozen=True)
class OpenClawToolInvokeResponse:
    status_code: int
    payload: Dict[str, Any]


class OpenClawToolInvokeError(RuntimeError):
    def __init__(
        self,
        message: str,
        status_code: int,
        error_type: str,
        details: Optional[Dict[str, Any]] = None,
        retry_after_seconds: Optional[int] = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.error_type = error_type
        self.details = details
        self.retry_after_seconds = retry_after_seconds


def _parse_retry_after_seconds(value: Optional[str]) -> Optional[int]:
    if value is None:
        return None
    normalized = value.strip()
    if not normalized:
        return None
    try:
        return int(normalized)
    except ValueError:
        return None


def _read_json_payload(response: requests.Response) -> Dict[str, Any]:
    try:
        payload = response.json()
    except ValueError:
        payload = {"message": response.text.strip() or "OpenClaw response was not valid JSON."}
    if not isinstance(payload, dict):
        return {"message": json.dumps(payload)}
    return payload


def _extract_error_code(payload: Dict[str, Any]) -> Optional[str]:
    error = payload.get("error")
    if isinstance(error, dict):
        code = error.get("code")
        if isinstance(code, str) and code.strip():
            return code.strip()
    code = payload.get("code")
    if isinstance(code, str) and code.strip():
        return code.strip()
    return None


def _extract_error_message(payload: Dict[str, Any], default: str) -> str:
    error = payload.get("error")
    if isinstance(error, dict):
        message = error.get("message")
        if isinstance(message, str) and message.strip():
            return message.strip()
    message = payload.get("message")
    if isinstance(message, str) and message.strip():
        return message.strip()
    return default


def _extract_error_details(payload: Dict[str, Any], fallback_code: Optional[str]) -> Optional[Dict[str, Any]]:
    details: Dict[str, Any] = {}
    error = payload.get("error")
    if isinstance(error, dict):
        nested_details = error.get("details")
        if isinstance(nested_details, dict):
            details.update(nested_details)
        elif nested_details is not None:
            details["details"] = nested_details
    top_details = payload.get("details")
    if isinstance(top_details, dict):
        details.update(top_details)
    elif top_details is not None:
        details["details"] = top_details
    if fallback_code and "code" not in details:
        details["code"] = fallback_code
    return details or None


def _map_error_type(status_code: int, error_code: Optional[str]) -> str:
    normalized_code = (error_code or "").upper()
    if "POLICY_DENIED" in normalized_code:
        return "policy_denied"
    if status_code in (401, 403):
        return "unauthorized"
    if status_code == 429:
        return "rate_limited"
    if status_code == 400:
        return "validation_error"
    return "tool_execution_error"


def invoke_openclaw_tools_api(
    base_url: str,
    api_key: str,
    request: OpenClawToolInvokeRequest,
    timeout_seconds: int = 30,
    account_id: Optional[str] = None,
    channel_id: Optional[str] = None,
) -> OpenClawToolInvokeResponse:
    normalized_base = (base_url or "").strip().rstrip("/")
    if not normalized_base.startswith(("http://", "https://")):
        raise ValueError("base_url must start with http:// or https://")

    normalized_key = (api_key or "").strip()
    if not normalized_key:
        raise ValueError("api_key cannot be empty")

    if not request.name.strip():
        raise ValueError("request.name cannot be empty")

    endpoint = f"{normalized_base}/tools/invoke"
    headers = {
        "Authorization": f"Bearer {normalized_key}",
        "Content-Type": "application/json",
    }
    if account_id and account_id.strip():
        headers["x-openclaw-account-id"] = account_id.strip()
    if channel_id and channel_id.strip():
        headers["x-openclaw-channel-id"] = channel_id.strip()

    response = requests.post(
        endpoint,
        json={"name": request.name, "arguments": request.arguments},
        headers=headers,
        timeout=timeout_seconds,
    )
    payload = _read_json_payload(response)
    if 200 <= response.status_code < 300:
        return OpenClawToolInvokeResponse(status_code=response.status_code, payload=payload)

    error_code = _extract_error_code(payload)
    error_type = _map_error_type(response.status_code, error_code)
    message = _extract_error_message(
        payload,
        default=f"OpenClaw /tools/invoke failed with HTTP {response.status_code}.",
    )
    details = _extract_error_details(payload, fallback_code=error_code)
    retry_after_seconds = _parse_retry_after_seconds(response.headers.get("Retry-After"))
    raise OpenClawToolInvokeError(
        message=message,
        status_code=response.status_code,
        error_type=error_type,
        details=details,
        retry_after_seconds=retry_after_seconds,
    )
