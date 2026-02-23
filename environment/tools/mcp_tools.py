import json
from typing import Any, Dict, Optional

from environment.mcp_client import MCPClientError, invoke_mcp_tool_stdio


def invoke_mcp_tool(
    server_command: str,
    tool_name: str,
    tool_arguments: Optional[Dict[str, Any]] = None,
    timeout_seconds: int = 30,
    working_directory: Optional[str] = None,
    require_listed_tool: bool = True,
) -> str:
    """
    Invoke a tool exposed by an external MCP stdio server.

    Returns JSON-encoded MCP tools/call result payload so downstream tools can parse it.
    """
    try:
        result = invoke_mcp_tool_stdio(
            server_command=server_command,
            tool_name=tool_name,
            tool_arguments=tool_arguments or {},
            timeout_seconds=timeout_seconds,
            working_directory=working_directory,
            require_listed_tool=require_listed_tool,
        )
    except MCPClientError as exc:
        raise RuntimeError(str(exc)) from exc
    return json.dumps(result, sort_keys=True)


INVOKE_MCP_TOOL_SCHEMA = {
    "name": "invoke_mcp_tool",
    "description": "Invoke a tool on an external MCP stdio server and return its JSON result payload.",
    "parameters": {
        "type": "object",
        "properties": {
            "server_command": {"type": "string", "minLength": 1},
            "tool_name": {"type": "string", "minLength": 1},
            "tool_arguments": {"type": "object"},
            "timeout_seconds": {"type": "integer", "minimum": 1, "maximum": 120},
            "working_directory": {"type": "string", "minLength": 1},
            "require_listed_tool": {"type": "boolean"},
        },
        "required": ["server_command", "tool_name"],
        "additionalProperties": False,
    },
}
