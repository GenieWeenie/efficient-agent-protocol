"""03_retry_and_recovery.py
Retry + failure propagation behavior.

Run:
    python3 -m examples.03_retry_and_recovery
"""

import asyncio
import os

from eap.environment import AsyncLocalExecutor, ToolRegistry
from eap.protocol import BatchedMacroRequest, RetryPolicy, StateManager, ToolCall


DB_PATH = "examples/.example_retry.db"


class FlakyTool:
    def __init__(self) -> None:
        self.calls = 0

    def __call__(self, value: str) -> str:
        self.calls += 1
        if self.calls == 1:
            raise RuntimeError("transient failure")
        return f"OK:{value}"


def always_fail(value: str) -> str:
    raise RuntimeError("hard failure")


TOOL_SCHEMA = {
    "name": "unstable_tool",
    "parameters": {
        "type": "object",
        "properties": {"value": {"type": "string"}},
        "required": ["value"],
    },
}


async def run_success_after_retry() -> None:
    state_manager = StateManager(db_path=DB_PATH)
    registry = ToolRegistry()
    registry.register("unstable_tool", FlakyTool(), TOOL_SCHEMA)
    executor = AsyncLocalExecutor(state_manager, registry)

    macro = BatchedMacroRequest(
        steps=[ToolCall(step_id="retry_step", tool_name="unstable_tool", arguments={"value": "demo"})],
        retry_policy=RetryPolicy(max_attempts=2, initial_delay_seconds=0.0, backoff_multiplier=1.0),
    )

    result = await executor.execute_macro(macro)
    print("Retry path pointer:", result["pointer_id"])
    print("Retry run ID:", result.get("metadata", {}).get("execution_run_id"))


async def run_dependency_failure() -> None:
    state_manager = StateManager(db_path=DB_PATH)
    registry = ToolRegistry()
    registry.register("unstable_tool", always_fail, TOOL_SCHEMA)
    executor = AsyncLocalExecutor(state_manager, registry)

    macro = BatchedMacroRequest(
        steps=[
            ToolCall(step_id="fail_first", tool_name="unstable_tool", arguments={"value": "x"}),
            ToolCall(step_id="blocked", tool_name="unstable_tool", arguments={"value": "$step:fail_first"}),
        ],
        retry_policy=RetryPolicy(max_attempts=1, initial_delay_seconds=0.0, backoff_multiplier=1.0),
    )

    result = await executor.execute_macro(macro)
    print("Dependency failure pointer:", result["pointer_id"])
    print("Failure metadata:", result.get("metadata"))


async def main() -> None:
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
    await run_success_after_retry()
    await run_dependency_failure()


if __name__ == "__main__":
    asyncio.run(main())
