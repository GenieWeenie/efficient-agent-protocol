# examples/new_efficient_flow.py
import json
import asyncio

from eap.protocol import StateManager
from eap.environment import AsyncLocalExecutor, ToolRegistry
from eap.agent import AgentClient

# --- 1. Define the Heavy Tools & Schemas ---
def dummy_fetch(query: str):
    print(f"      [TOOL: fetch_user_data] -> Hitting database for: {query}")
    return f"MASSIVE_RAW_DATABASE_DUMP_FOR_{query.upper()}" * 100

def dummy_analyze(raw_data: str, focus: str):
    print(f"      [TOOL: analyze_data] -> Analyzing massive payload for: {focus}")
    return f"Analysis complete. Found requested metrics regarding '{focus}' in the raw data."

fetch_schema = {
    "name": "fetch_user_data",
    "description": "Fetches massive amounts of raw data from the database.",
    "parameters": {
        "type": "object",
        "properties": {"query": {"type": "string"}},
        "required": ["query"]
    }
}

analyze_schema = {
    "name": "analyze_data",
    "description": "Analyzes raw data based on a specific focus.",
    "parameters": {
        "type": "object",
        "properties": {
            "raw_data": {"type": "string"},
            "focus": {"type": "string"}
        },
        "required": ["raw_data", "focus"]
    }
}

async def main():
    print("\n========================================================")
    print("🚀 EFFICIENT AGENT PROTOCOL (EAP) - END-TO-END TEST")
    print("========================================================\n")

    print("[SYSTEM] Booting local async environment...")
    state_manager = StateManager()
    registry = ToolRegistry()
    executor = AsyncLocalExecutor(state_manager=state_manager, registry=registry)

    registry.register("fetch_user_data", dummy_fetch, fetch_schema)
    registry.register("analyze_data", dummy_analyze, analyze_schema)
    
    # --- THE FIX: Give the LLM the hashed ID AND the parameters ---
    hashed_names = registry.get_hashed_manifest()
    full_schemas = registry.get_full_schemas()
    
    agent_manifest = {}
    for name, hash_id in hashed_names.items():
        # We strip out the heavy descriptions but keep the required arguments
        agent_manifest[hash_id] = full_schemas[name]["parameters"]

    print("[SYSTEM] Booting Universal LLM Agent Client...")
    
    # --- THE FIX: Add a few-shot example for the smaller 3B model ---
    system_prompt = (
        "You are an elite, highly optimized local autonomous agent.\n"
        "EXAMPLE OUTPUT FORMAT:\n"
        "{\n"
        "  \"steps\": [\n"
        "    {\"step_id\": \"step_1\", \"tool_name\": \"hashed_tool_1\", \"arguments\": {\"query\": \"financial_records\"}},\n"
        "    {\"step_id\": \"step_2\", \"tool_name\": \"hashed_tool_2\", \"arguments\": {\"raw_data\": \"$step:step_1\", \"focus\": \"Q4 Revenue\"}}\n"
        "  ],\n"
        "  \"return_final_state_only\": true\n"
        "}"
    )
    
    agent = AgentClient(
        base_url="http://localhost:1234", 
        model_name="your-local-model-name", 
        system_prompt=system_prompt
    )

    user_prompt = "Can you fetch the financial records and analyze them for Q4 Revenue?"
    print(f"\n[USER] {user_prompt}\n")

    # Pass our newly combined manifest so the LLM knows what arguments to use
    compiled_macro = agent.generate_macro(user_prompt, agent_manifest)
    
    print("\n[LLM] Generated the following Stateful Batched Protocol (SBP) Macro:")
    print(compiled_macro.model_dump_json(indent=2))
    
    print("\n[ENVIRONMENT] Intercepting macro and running local asynchronous DAG...")
    final_pointer = await executor.execute_macro(compiled_macro)

    print("\n========================================================")
    print("✅ FINAL RESULT RETURNED TO LLM CONTEXT WINDOW:")
    print(json.dumps(final_pointer, indent=2))
    print("========================================================\n")

if __name__ == "__main__":
    asyncio.run(main())