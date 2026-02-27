# Examples

Progressive examples from minimal to advanced.

## Core Examples (Start Here)

| File | Description |
| --- | --- |
| `01_minimal.py` | Minimal single-step workflow |
| `02_multi_tool_dag.py` | Multi-tool DAG with parallel execution |
| `03_retry_and_recovery.py` | Retry logic and error recovery |

## Extended Examples

| File | Description |
| --- | --- |
| `new_efficient_flow.py` | End-to-end efficient workflow |
| `self_healing_flow.py` | Self-healing workflow with automatic recovery |
| `multi_agent_handshake.py` | Multi-agent coordination handshake |
| `real_file_test.py` | Real file I/O operations |
| `web_voyager_test.py` | Web interaction workflow |
| `view_state.py` | Inspect pointer state and stored data |

## Demo Scripts

| File | Description |
| --- | --- |
| `demo_registry.py` | Tool registry usage and manifest generation |
| `demo_async_dag.py` | Async DAG execution walkthrough |
| `demo_executor.py` | Executor setup and step execution |
| `legacy_ping_pong.py` | Legacy ping-pong flow (kept for reference) |

## Plugin Example

The `plugins/sample_plugin/` directory contains a complete example of a third-party EAP plugin.
See `plugins/sample_plugin/README.md` and `docs/plugin_spec.md` for the plugin contract.

## Running Examples

```bash
# Run any example as a module
python -m examples.01_minimal
python -m examples.02_multi_tool_dag
python -m examples.03_retry_and_recovery
```

Make sure you have a `.env` file configured (see the [Quickstart](../README.md#quickstart-github-first) in the main README).
