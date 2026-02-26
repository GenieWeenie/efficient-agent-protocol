# Custom Tool Authoring

This guide explains how to add tools that run safely inside the EAP executor.

## What A Tool Is In EAP

A tool is:

1. A Python callable.
2. A JSON schema contract.
3. A registry entry in `ToolRegistry`.

At runtime, EAP validates step arguments against the schema, resolves pointer references, and then invokes the callable.

## Minimum Authoring Pattern

```python
import asyncio

from eap.environment import AsyncLocalExecutor, ToolRegistry
from eap.protocol import BatchedMacroRequest, StateManager, ToolCall


def summarize_text(text: str, max_words: int = 30) -> str:
    words = text.split()
    return " ".join(words[:max_words])


SUMMARIZE_SCHEMA = {
    "name": "summarize_text",
    "description": "Summarize plain text content.",
    "parameters": {
        "type": "object",
        "properties": {
            "text": {"type": "string", "minLength": 1},
            "max_words": {"type": "integer", "minimum": 1, "maximum": 200},
        },
        "required": ["text"],
        "additionalProperties": False,
    },
}


async def main() -> None:
    state = StateManager(db_path="examples/.custom_tool.db")
    registry = ToolRegistry()
    registry.register("summarize_text", summarize_text, SUMMARIZE_SCHEMA)
    executor = AsyncLocalExecutor(state, registry)

    macro = BatchedMacroRequest(
        steps=[
            ToolCall(
                step_id="s1",
                tool_name="summarize_text",
                arguments={"text": "EAP custom tools run behind schema validation."},
            )
        ]
    )
    result = await executor.execute_macro(macro)
    print(result["pointer_id"], state.retrieve(result["pointer_id"]))


if __name__ == "__main__":
    asyncio.run(main())
```

## Schema Contract Rules (Enforced)

`ToolRegistry.register(...)` enforces these checks:

- `schema["name"]` must exactly match the registration name.
- `schema["parameters"]` must be an object schema.
- `schema["parameters"]["properties"]` must be a dictionary.
- `required` entries must all exist in `properties`.
- `additionalProperties` must be a boolean if present.

`ToolRegistry.validate_arguments(...)` enforces runtime argument checks:

- required fields
- primitive `type` checks (`string`, `boolean`, `integer`, `number`, `object`, `array`)
- `enum`
- `minLength` / `maxLength`
- `minimum` / `maximum`
- `minItems` / `maxItems`
- `additionalProperties: false`

## Pointer-Aware Arguments

Executor argument resolution supports:

- `"$step:<step_id>"` (or `"$<step_id>"`) to consume another step output.
- Direct pointer IDs (`"ptr_..."`) to consume existing persisted data.

Important behavior:

- Dependency step must complete with status `ok`; otherwise dependency resolution fails.
- Resolved pointer values are loaded through `StateManager.retrieve(...)` before tool call.
- Stored pointer payloads are raw strings, so tools should parse JSON explicitly when needed.

## Planner Manifest And Hashed Tool IDs

`ToolRegistry` generates deterministic hashed IDs from tool schema (for example `read_local_file_a1b2c3d4`).

- `get_hashed_manifest()` returns `{tool_name: hashed_tool_id}`.
- `get_agent_manifest()` returns `{hashed_tool_id: parameters_schema}`.

Use the agent manifest for planner prompts to keep context small while preserving schema fidelity.

## Plugin Authoring (Entry Point Path)

For reusable external tool packs:

1. Build a manifest with `plugin_name` and a `tools` list.
2. Each tool entry must include `name`, `function`, and `schema`.
3. Expose the manifest via Python entry points group `eap.tool_plugins`.
4. Load with `ToolRegistry(auto_load_plugins=True)` or `registry.load_plugins(...)`.

Reference implementation:

- `examples/plugins/sample_plugin/sample_plugin/__init__.py`
- `environment/plugin_loader.py`

## Testing Checklist

1. Unit-test schema validation failures (`InputValidationError`).
2. Integration-test end-to-end macro execution with your tool.
3. Validate retry behavior if the tool can fail transiently.
4. Validate pointer-input behavior (`$step:*` and `ptr_*` inputs).

Suggested existing suites to copy:

- `tests/unit/test_tool_registry.py`
- `tests/integration/test_pointer_flow.py`
- `tests/integration/test_executor_retries.py`

## Common Failure Modes

- `PluginManifestError`: schema/name contract mismatch at registration time.
- `InputValidationError`: runtime arguments violate schema.
- `KeyError` during dependency resolution: referenced step did not complete successfully.
- `tool_execution_error`: callable raised an exception after validation.
