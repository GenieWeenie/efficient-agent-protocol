from __future__ import annotations

import argparse
import asyncio
import json
import os
import tempfile
from pathlib import Path
from typing import Any, Dict, Optional

from eap.environment import AsyncLocalExecutor, ToolRegistry
from eap.environment.tools import (
    ANALYZE_SCHEMA,
    READ_FILE_SCHEMA,
    WRITE_FILE_SCHEMA,
    analyze_data,
    read_local_file,
    write_local_file,
)
from eap.protocol import BatchedMacroRequest, StateManager, ToolCall


def run_doc_ops(
    input_file: str,
    output_file: str,
    focus: str = "extract concise summary and action items",
    db_path: Optional[str] = None,
) -> Dict[str, Any]:
    input_path = Path(input_file).resolve()
    if not input_path.exists():
        raise FileNotFoundError(f"Doc ops input file does not exist: {input_path}")

    output_path = Path(output_file).resolve()

    owns_db = db_path is None
    if owns_db:
        fd, generated_path = tempfile.mkstemp(prefix="eap-starter-docops-", suffix=".db")
        os.close(fd)
        db_path = generated_path

    state_manager = StateManager(db_path=db_path)
    registry = ToolRegistry()
    registry.register("read_local_file", read_local_file, READ_FILE_SCHEMA)
    registry.register("analyze_data", analyze_data, ANALYZE_SCHEMA)
    registry.register("write_local_file", write_local_file, WRITE_FILE_SCHEMA)
    executor = AsyncLocalExecutor(state_manager, registry)

    try:
        macro = BatchedMacroRequest(
            steps=[
                ToolCall(
                    step_id="read_source_doc",
                    tool_name="read_local_file",
                    arguments={"file_path": str(input_path)},
                ),
                ToolCall(
                    step_id="build_doc_summary",
                    tool_name="analyze_data",
                    arguments={
                        "raw_data": "$step:read_source_doc",
                        "focus": focus,
                    },
                ),
                ToolCall(
                    step_id="write_report",
                    tool_name="write_local_file",
                    arguments={
                        "file_path": str(output_path),
                        "content": "$step:build_doc_summary",
                        "mode": "overwrite",
                        "create_directories": True,
                    },
                ),
            ]
        )
        result = asyncio.run(executor.execute_macro(macro))
        report = output_path.read_text(encoding="utf-8")
        return {
            "input_file": str(input_path),
            "output_file": str(output_path),
            "focus": focus,
            "report": report,
            "run_id": result["metadata"]["execution_run_id"],
            "pointer_id": result["pointer_id"],
        }
    finally:
        if owns_db and db_path and os.path.exists(db_path):
            os.remove(db_path)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the doc-ops starter pack on a local markdown/text file.")
    parser.add_argument(
        "--input-file",
        default="docs/starter_packs/fixtures/doc_ops_notes.md",
        help="Path to input markdown/text file.",
    )
    parser.add_argument(
        "--output-file",
        default="artifacts/starter_pack_doc_ops/report.md",
        help="Path for generated summary/action report.",
    )
    parser.add_argument(
        "--focus",
        default="extract concise summary and action items",
        help="Analysis focus instruction.",
    )
    parser.add_argument(
        "--db-path",
        default=None,
        help="Optional SQLite state DB path (temporary by default).",
    )
    args = parser.parse_args()
    payload = run_doc_ops(
        input_file=args.input_file,
        output_file=args.output_file,
        focus=args.focus,
        db_path=args.db_path,
    )
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
