# examples/self_healing_flow.py
import asyncio
import json

from eap.protocol import StateManager
from eap.environment import AsyncLocalExecutor, ToolRegistry
from eap.agent import AgentClient

# --- Tool with strict validation ---
def strict_tool(correct_key: str):
    # This tool will ONLY work if the LLM uses the key 'correct_key'
    return f"Success! You used the right key: {correct_key}"

STRICT_SCHEMA = {
    "name": "strict_tool",
    "description": "Requires the exact parameter 'correct_key'.",
    "parameters": {
        "type": "object",
        "properties": {"correct_key": {"type": "string"}},
        "required": ["correct_key"]
    }
}

async def main():
    print("--- 🩹 Starting Self-Healing Flow Test ---")
    
    state_manager = StateManager()
    registry = ToolRegistry()
    registry.register("strict_tool", strict_tool, STRICT_SCHEMA)
    
    # Intentionally messy manifest to see if LLM can recover from errors
    hashed_manifest = {
        registry.get_hashed_manifest()["strict_tool"]: STRICT_SCHEMA["parameters"]
    }

    agent = AgentClient(
        base_url="http://localhost:1234", 
        model_name="your-local-model-name",
        system_prompt="You are an elite agent. Always double check parameter names."
    )

    executor = AsyncLocalExecutor(state_manager, registry)
    
    user_query = "Run the strict tool with the value 'CastleWyvern'."
    error_message = None
    max_retries = 3
    
    for attempt in range(max_retries):
        try:
            print(f"\n[LOOP] Attempt {attempt + 1}...")
            
            # 1. Generate Macro (including error feedback if it exists)
            macro = agent.generate_macro(user_query, hashed_manifest, error_feedback=error_message)
            
            # 2. Try to execute
            result = await executor.execute_macro(macro)
            
            print("\n✅ HEALED! Final Result:")
            print(json.dumps(result, indent=2))
            break # Exit loop on success
            
        except Exception as e:
            print(f"❌ EXECUTION FAILED: {str(e)}")
            # Capture the error to send back to the LLM in the next iteration
            error_message = str(e)
            if attempt == max_retries - 1:
                print("Max retries reached. System could not self-heal.")

if __name__ == "__main__":
    asyncio.run(main())