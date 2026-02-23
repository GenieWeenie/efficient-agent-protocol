"""01_minimal.py
Minimal end-to-end macro execution with one tool call.

Run:
    python3 -m examples.01_minimal
"""

import asyncio
import os

from eap.environment import AsyncLocalExecutor, ToolRegistry
from eap.protocol import BatchedMacroRequest, RetryPolicy, StateManager, ToolCall


DB_PATH = "examples/.example_minimal.db"


def echo_text(text: str) -> str:
    return f"ECHO:{text}"


ECHO_SCHEMA = {
    "name": "echo_text",
    "parameters": {
        "type": "object",
        "properties": {"text": {"type": "string"}},
        "required": ["text"],
    },
}


async def main() -> None:
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)

    state_manager = StateManager(db_path=DB_PATH)
    registry = ToolRegistry()
    registry.register("echo_text", echo_text, ECHO_SCHEMA)
    executor = AsyncLocalExecutor(state_manager, registry)

    macro = BatchedMacroRequest(
        steps=[ToolCall(step_id="step_echo", tool_name="echo_text", arguments={"text": "hello eap"})],
        retry_policy=RetryPolicy(max_attempts=1, initial_delay_seconds=0.0, backoff_multiplier=1.0),
    )

    result = await executor.execute_macro(macro)
    payload = state_manager.retrieve(result["pointer_id"])

    print("Final pointer:", result["pointer_id"])
    print("Payload:", payload)


if __name__ == "__main__":
    asyncio.run(main())
