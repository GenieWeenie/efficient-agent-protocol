"""02_multi_tool_dag.py
Parallel multi-step DAG with pointer chaining.

Run:
    python3 -m examples.02_multi_tool_dag
"""

import asyncio
import os
import time

from eap.environment import AsyncLocalExecutor, ToolRegistry
from eap.protocol import BatchedMacroRequest, RetryPolicy, StateManager, ToolCall


DB_PATH = "examples/.example_dag.db"


def fetch_data(source: str) -> str:
    time.sleep(0.1)
    return f"DATA[{source}]"


def merge_data(left: str, right: str) -> str:
    return f"MERGED<{left}|{right}>"


FETCH_SCHEMA = {
    "name": "fetch_data",
    "parameters": {
        "type": "object",
        "properties": {"source": {"type": "string"}},
        "required": ["source"],
    },
}

MERGE_SCHEMA = {
    "name": "merge_data",
    "parameters": {
        "type": "object",
        "properties": {
            "left": {"type": "string"},
            "right": {"type": "string"},
        },
        "required": ["left", "right"],
    },
}


async def main() -> None:
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)

    state_manager = StateManager(db_path=DB_PATH)
    registry = ToolRegistry()
    registry.register("fetch_data", fetch_data, FETCH_SCHEMA)
    registry.register("merge_data", merge_data, MERGE_SCHEMA)
    executor = AsyncLocalExecutor(state_manager, registry)

    macro = BatchedMacroRequest(
        steps=[
            ToolCall(step_id="fetch_a", tool_name="fetch_data", arguments={"source": "alpha"}),
            ToolCall(step_id="fetch_b", tool_name="fetch_data", arguments={"source": "beta"}),
            ToolCall(
                step_id="merge",
                tool_name="merge_data",
                arguments={"left": "$step:fetch_a", "right": "$step:fetch_b"},
            ),
        ],
        retry_policy=RetryPolicy(max_attempts=1, initial_delay_seconds=0.0, backoff_multiplier=1.0),
    )

    result = await executor.execute_macro(macro)
    payload = state_manager.retrieve(result["pointer_id"])

    print("Final pointer:", result["pointer_id"])
    print("Merged payload:", payload)
    print("Run ID:", result.get("metadata", {}).get("execution_run_id"))


if __name__ == "__main__":
    asyncio.run(main())
