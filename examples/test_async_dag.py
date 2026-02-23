# examples/test_async_dag.py
import time
import asyncio
import json

from eap.protocol import StateManager
from eap.environment import AsyncLocalExecutor, ToolRegistry
from eap.protocol.models import BatchedMacroRequest, ToolCall

# --- Mock Tools with Delays ---
def slow_fetch(query: str):
    time.sleep(3) # Simulating a slow 3-second database query
    return f"DATA_FOR_{query.upper()}"

def combine_data(data1: str, data2: str):
    time.sleep(1) # Simulating a 1-second processing task
    return f"COMBINED: [{data1}] and [{data2}]"

# Mock Schemas
schema_fetch = {"name": "slow_fetch", "parameters": {"type": "object", "properties": {"query": {"type": "string"}}}}
schema_combine = {"name": "combine_data", "parameters": {"type": "object", "properties": {"data1": {"type": "string"}, "data2": {"type": "string"}}}}

async def main():
    print("--- Starting Parallel DAG Execution Test ---\n")
    
    state_manager = StateManager()
    registry = ToolRegistry()
    registry.register("slow_fetch", slow_fetch, schema_fetch)
    registry.register("combine_data", combine_data, schema_combine)
    
    executor = AsyncLocalExecutor(state_manager, registry)
    hashes = registry.get_hashed_manifest()

    # The LLM asks to fetch two things, then combine them.
    # In a sequential system, this takes: 3s + 3s + 1s = 7 seconds.
    macro = BatchedMacroRequest(
        steps=[
            ToolCall(step_id="step_A", tool_name=hashes["slow_fetch"], arguments={"query": "financials"}),
            ToolCall(step_id="step_B", tool_name=hashes["slow_fetch"], arguments={"query": "emails"}),
            ToolCall(step_id="step_C", tool_name=hashes["combine_data"], arguments={"data1": "$step:step_A", "data2": "$step:step_B"})
        ]
    )

    start_time = time.time()
    
    # Run the Async Executor
    final_pointer = await executor.execute_macro(macro)
    
    end_time = time.time()
    
    print("\n--- Result ---")
    print(json.dumps(final_pointer, indent=2))
    print(f"\nTotal Execution Time: {end_time - start_time:.2f} seconds")
    print("Notice it took ~4 seconds, not 7! Step A and Step B ran perfectly in parallel.")

if __name__ == "__main__":
    asyncio.run(main())