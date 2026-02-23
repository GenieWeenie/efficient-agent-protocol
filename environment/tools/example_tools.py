# environment/tools/example_tools.py
import logging

logger = logging.getLogger("eap.environment.tools.example_tools")


def fetch_user_data(query: str) -> str:
    logger.info(
        "tool invoked",
        extra={"tool_name": "fetch_user_data"},
    )
    return f"MASSIVE_RAW_DATABASE_DUMP_FOR_{query.upper()}" * 100

def analyze_data(raw_data: str, focus: str) -> str:
    logger.info(
        "tool invoked",
        extra={"tool_name": "analyze_data"},
    )
    return f"Analysis complete. Found requested metrics regarding '{focus}' in the raw data."

FETCH_SCHEMA = {
    "name": "fetch_user_data",
    "description": "Fetches massive amounts of raw data from the database.",
    "parameters": {
        "type": "object",
        "properties": {"query": {"type": "string"}},
        "required": ["query"]
    }
}

ANALYZE_SCHEMA = {
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
