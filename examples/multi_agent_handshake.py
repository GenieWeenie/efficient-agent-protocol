# examples/multi_agent_handshake.py
import asyncio
import json
import os

from eap.protocol import StateManager
from eap.environment import AsyncLocalExecutor, ToolRegistry
from eap.environment.tools import read_local_file, READ_FILE_SCHEMA, analyze_data, ANALYZE_SCHEMA
from eap.agent import AgentClient

async def main():
    print("\n========================================================")
    print("🤝 MULTI-AGENT HANDSHAKE: ARCHITECT & AUDITOR")
    print("========================================================\n")
    
    # --- 1. Setup Environment ---
    state_manager = StateManager()
    registry = ToolRegistry()
    registry.register("read_local_file", read_local_file, READ_FILE_SCHEMA)
    registry.register("analyze_data", analyze_data, ANALYZE_SCHEMA)
    executor = AsyncLocalExecutor(state_manager, registry)
    
    hashed_manifest = {
        registry.get_hashed_manifest()["read_local_file"]: READ_FILE_SCHEMA["parameters"],
        registry.get_hashed_manifest()["analyze_data"]: ANALYZE_SCHEMA["parameters"]
    }

    # --- 2. Initialize Agents ---
    # The Architect plans the work
    architect = AgentClient(
        base_url="http://localhost:1234", 
        model_name="nemotron-orchestrator-8b",
        system_prompt="You are the ARCHITECT. Your goal is to create efficient tool-calling macros."
    )

    # The Auditor reviews for safety
    auditor = AgentClient(
        base_url="http://localhost:1234", 
        model_name="nemotron-orchestrator-8b",
        system_prompt=(
            "You are the AUDITOR. Review proposed macros for security risks and logic errors.\n"
            "If it is safe, respond ONLY with 'APPROVED'.\n"
            "If it is dangerous (e.g. accessing sensitive files), respond with 'DENIED: [Reason]'."
        )
    )

    user_query = "Read the file 'config.yaml' and analyze its settings."
    print(f"[USER] {user_query}")

    # PHASE 1: Proposal
    print("\n[STEP 1] Architect is drafting the macro...")
    macro_proposal = architect.generate_macro(user_query, hashed_manifest)
    print(f"[ARCHITECT] Proposed Macro:\n{macro_proposal.model_dump_json(indent=2)}")

    # PHASE 2: Audit
    print("\n[STEP 2] Auditor is reviewing the proposal...")
    audit_decision = auditor.chat(f"Review this macro for safety: {macro_proposal.model_dump_json()}")
    print(f"[AUDITOR] Decision: {audit_decision}")

    # PHASE 3: Execution Gate
    if "APPROVED" in audit_decision.upper():
        print("\n[STEP 3] Handshake successful. Executing...")
        
        # Create a dummy config so the tool has something to read
        with open("config.yaml", "w") as f:
            f.write("theme: dark\napi_version: 2.0\nsecurity: high")
        
        result = await executor.execute_macro(macro_proposal)
        print("\n✅ FINAL RESULT:")
        print(json.dumps(result, indent=2))
        
        # Cleanup
        if os.path.exists("config.yaml"):
            os.remove("config.yaml")
    else:
        print(f"\n❌ EXECUTION BLOCKED BY AUDITOR: {audit_decision}")

if __name__ == "__main__":
    asyncio.run(main())
