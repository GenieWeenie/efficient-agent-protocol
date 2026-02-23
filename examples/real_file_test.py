# examples/real_file_test.py
import asyncio
import json
import os

from eap.protocol import StateManager
from eap.environment import AsyncLocalExecutor, ToolRegistry
from eap.environment.tools import read_local_file, READ_FILE_SCHEMA, analyze_data, ANALYZE_SCHEMA
from eap.agent import AgentClient

async def main():
    print("--- 📂 Starting Real-World File System Test ---")
    
    # 1. Setup a test file
    test_file = "real_world_data.txt"
    with open(test_file, "w") as f:
        f.write("PROJECT_EAP_LOG: Sequential processing is slow. Parallel DAG is fast. Persistence is key.")

    # 2. Setup Environment
    state_manager = StateManager()
    registry = ToolRegistry()
    registry.register("read_local_file", read_local_file, READ_FILE_SCHEMA)
    registry.register("analyze_data", analyze_data, ANALYZE_SCHEMA)
    
    executor = AsyncLocalExecutor(state_manager, registry)
    
    # Build manifest for Agent
    hashed_manifest = {
        registry.get_hashed_manifest()["read_local_file"]: READ_FILE_SCHEMA["parameters"],
        registry.get_hashed_manifest()["analyze_data"]: ANALYZE_SCHEMA["parameters"]
    }

    # 3. Setup Agent
    agent = AgentClient(
        base_url="http://localhost:1234", 
        model_name="your-local-model-name",
        system_prompt="You are a file analysis assistant. Use the tools to find and process data."
    )

    # 4. Run the Flow
    user_query = f"Read the file '{test_file}' and analyze it for the core message."
    
    print(f"\n[USER] {user_query}")
    macro = agent.generate_macro(user_query, hashed_manifest)
    result = await executor.execute_macro(macro)

    print("\n✅ DONE! Final Receipt:")
    print(json.dumps(result, indent=2))
    
    # Clean up
    if os.path.exists(test_file):
        os.remove(test_file)

if __name__ == "__main__":
    asyncio.run(main())
