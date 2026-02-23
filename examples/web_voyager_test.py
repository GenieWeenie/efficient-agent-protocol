# examples/web_voyager_test.py
import asyncio
import json

from eap.protocol import StateManager
from eap.environment import AsyncLocalExecutor, ToolRegistry
from eap.environment.tools import scrape_url, SCRAPE_SCHEMA, analyze_data, ANALYZE_SCHEMA
from eap.agent import AgentClient

async def main():
    print("--- 🌐 Starting Web Voyager Test ---")
    
    state_manager = StateManager()
    registry = ToolRegistry()
    registry.register("scrape_url", scrape_url, SCRAPE_SCHEMA)
    registry.register("analyze_data", analyze_data, ANALYZE_SCHEMA)
    executor = AsyncLocalExecutor(state_manager, registry)
    
    hashed_manifest = {
        registry.get_hashed_manifest()["scrape_url"]: SCRAPE_SCHEMA["parameters"],
        registry.get_hashed_manifest()["analyze_data"]: ANALYZE_SCHEMA["parameters"]
    }

    agent = AgentClient(
        base_url="http://localhost:1234", 
        model_name="your-local-model-name",
        system_prompt="You are a web research assistant. Use the scraper to gather info."
    )

    user_query = "Go to 'https://www.python.org/about/' and tell me the core mission of Python."
    
    print(f"\n[USER] {user_query}")
    macro = agent.generate_macro(user_query, hashed_manifest)
    result = await executor.execute_macro(macro)

    print("\n✅ RESEARCH COMPLETE! Final Receipt:")
    print(json.dumps(result, indent=2))

if __name__ == "__main__":
    asyncio.run(main())