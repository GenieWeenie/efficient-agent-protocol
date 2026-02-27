# examples/test_registry.py
import json

from eap.protocol.state_manager import StateManager
from eap.environment.executor import LocalExecutor
from eap.environment.tool_registry import ToolRegistry
from eap.protocol.models import BatchedMacroRequest, ToolCall

# --- Dummy Tools for Testing ---
def dummy_fetch(query: str):
    return f"MASSIVE_RAW_DATABASE_DUMP_FOR_{query.upper()}" * 100

def dummy_analyze(raw_data: str, focus: str):
    return f"Analysis complete. Found requested metrics regarding '{focus}' in the raw data."

def main():
    print("--- Starting Phase 3: Schema Hashing (The Tool Registry) ---\n")

    # 1. Initialize our environment and registry
    state_manager = StateManager()
    registry = ToolRegistry()
    
    # We pass the registry into the executor now
    executor = LocalExecutor(state_manager=state_manager, registry=registry)

    # 2. Define the heavy JSON schemas for our tools
    # In the "old way", this entire block gets sent to the LLM on every single message.
    fetch_schema = {
        "name": "fetch_user_data",
        "description": "Fetches massive amounts of raw data from the database.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "The search query."}
            },
            "required": ["query"]
        }
    }
    
    analyze_schema = {
        "name": "analyze_data",
        "description": "Analyzes raw data based on a specific focus.",
        "parameters": {
            "type": "object",
            "properties": {
                "raw_data": {"type": "string", "description": "The raw data to analyze."},
                "focus": {"type": "string", "description": "The metric to focus on."}
            },
            "required": ["raw_data", "focus"]
        }
    }

    # 3. Register the tools and their schemas
    print("[REGISTRY] Registering tools and generating lightweight hashes...")
    registry.register("fetch_user_data", dummy_fetch, fetch_schema)
    registry.register("analyze_data", dummy_analyze, analyze_schema)

    # 4. View the hashed manifest 
    # This short list is the ONLY thing the LLM needs to keep in context after the handshake.
    hashed_manifest = registry.get_hashed_manifest()
    print("\n[REGISTRY] Lightweight Hashed Manifest:")
    print(json.dumps(hashed_manifest, indent=2))
    
    # Get the actual hashed IDs to use in our test dynamically
    hashed_fetch_id = hashed_manifest["fetch_user_data"]
    hashed_analyze_id = hashed_manifest["analyze_data"]

    # 5. Simulate the LLM's Intent using the HASHED IDs
    print(f"\n[LLM] Sending batched macro using lightweight hashes instead of full names...\n")
    
    macro_request = BatchedMacroRequest(
        steps=[
            ToolCall(
                step_id="step_1_fetch",
                tool_name=hashed_fetch_id, # The LLM uses the short hash!
                arguments={"query": "financial_records"}
            ),
            ToolCall(
                step_id="step_2_analyze",
                tool_name=hashed_analyze_id, # The LLM uses the short hash!
                arguments={
                    "raw_data": "$step:step_1_fetch", 
                    "focus": "Q4 Revenue"
                }
            )
        ],
        return_final_state_only=True
    )

    # 6. Execute the macro
    final_pointer = executor.execute_macro(macro_request)

    print("\n[CLIENT] Macro execution complete. Sending final response to LLM:\n")
    print(json.dumps(final_pointer, indent=2))
    
    print("\n--- Result ---")
    print("Tools successfully executed using ONLY their hashed IDs, saving thousands of tokens per request.")

if __name__ == "__main__":
    main()