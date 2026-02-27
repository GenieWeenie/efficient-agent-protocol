# examples/test_executor.py
import json

from eap.protocol.state_manager import StateManager
from eap.environment.executor import LocalExecutor
from eap.protocol.models import BatchedMacroRequest, ToolCall

def main():
    print("--- Starting Phase 2: Executor Test (Killing the Ping-Pong) ---\n")

    # 1. Initialize our environment
    state_manager = StateManager()
    executor = LocalExecutor(state_manager=state_manager)

    # 2. Simulate the LLM's Intent
    print("[LLM] Sending a single batched macro to the client environment...\n")
    
    macro_request = BatchedMacroRequest(
        steps=[
            # Step 1: Fetch the heavy data
            ToolCall(
                step_id="step_1_fetch",
                tool_name="fetch_user_data",
                arguments={"query": "financial_records"}
            ),
            # Step 2: Analyze the heavy data. 
            # We use "$step:" to tell the executor to grab the output of step 1!
            ToolCall(
                step_id="step_2_analyze",
                tool_name="analyze_data",
                arguments={
                    "raw_data": "$step:step_1_fetch", 
                    "focus": "Q4 Revenue"
                }
            )
        ],
        return_final_state_only=True
    )

    # 3. The Client Environment executes the macro locally, resolving dependencies automatically
    final_pointer = executor.execute_macro(macro_request)

    # 4. What the LLM actually receives back
    print("\n[CLIENT] Macro execution complete. Sending final response to LLM:\n")
    print(json.dumps(final_pointer, indent=2))
    
    print("\n--- Result ---")
    print("Two tools executed sequentially on massive data with exactly ONE network round-trip.")

if __name__ == "__main__":
    main()