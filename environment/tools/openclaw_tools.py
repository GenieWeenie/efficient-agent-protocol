import json
from typing import Any, Dict, Optional

from environment.openclaw_client import (
    OpenClawToolInvokeError,
    OpenClawToolInvokeRequest,
    invoke_openclaw_tools_api,
)


def invoke_openclaw_tool(
    base_url: str,
    api_key: str,
    tool_name: str,
    tool_arguments: Optional[Dict[str, Any]] = None,
    timeout_seconds: int = 30,
    account_id: Optional[str] = None,
    channel_id: Optional[str] = None,
) -> str:
    """
    Invoke an OpenClaw gateway tool via HTTP `/tools/invoke`.

    Returns JSON-encoded payload from OpenClaw so downstream steps can parse it.
    """
    try:
        response = invoke_openclaw_tools_api(
            base_url=base_url,
            api_key=api_key,
            request=OpenClawToolInvokeRequest(
                name=tool_name,
                arguments=tool_arguments or {},
            ),
            timeout_seconds=timeout_seconds,
            account_id=account_id,
            channel_id=channel_id,
        )
    except OpenClawToolInvokeError as exc:
        message = (
            f"OpenClaw /tools/invoke failed ({exc.error_type}, status={exc.status_code}): {str(exc)}"
        )
        raise RuntimeError(message) from exc

    return json.dumps(response.payload, sort_keys=True)


INVOKE_OPENCLAW_TOOL_SCHEMA = {
    "name": "invoke_openclaw_tool",
    "description": "Invoke an OpenClaw gateway tool through HTTP /tools/invoke and return JSON response payload.",
    "parameters": {
        "type": "object",
        "properties": {
            "base_url": {"type": "string", "minLength": 1},
            "api_key": {"type": "string", "minLength": 1},
            "tool_name": {"type": "string", "minLength": 1},
            "tool_arguments": {"type": "object"},
            "timeout_seconds": {"type": "integer", "minimum": 1, "maximum": 120},
            "account_id": {"type": "string", "minLength": 1},
            "channel_id": {"type": "string", "minLength": 1},
        },
        "required": ["base_url", "api_key", "tool_name"],
        "additionalProperties": False,
    },
}
