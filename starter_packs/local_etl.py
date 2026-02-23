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
    READ_FILE_SCHEMA,
    WRITE_FILE_SCHEMA,
    read_local_file,
    write_local_file,
)
from eap.protocol import BatchedMacroRequest, StateManager, ToolCall


def transform_sales_jsonl(raw_data: str) -> str:
    rows = [line.strip() for line in raw_data.splitlines() if line.strip()]
    parsed_rows = [json.loads(row) for row in rows]
    total_amount = sum(float(row.get("amount", 0.0)) for row in parsed_rows)
    region_totals: Dict[str, float] = {}
    for row in parsed_rows:
        region = str(row.get("region", "unknown"))
        region_totals[region] = region_totals.get(region, 0.0) + float(row.get("amount", 0.0))

    payload = {
        "record_count": len(parsed_rows),
        "total_amount": round(total_amount, 2),
        "region_totals": {key: round(value, 2) for key, value in sorted(region_totals.items())},
    }
    return json.dumps(payload, indent=2, sort_keys=True)


TRANSFORM_SALES_SCHEMA = {
    "name": "transform_sales_jsonl",
    "description": "Transforms JSONL sales records into aggregate metrics.",
    "parameters": {
        "type": "object",
        "properties": {
            "raw_data": {"type": "string"},
        },
        "required": ["raw_data"],
        "additionalProperties": False,
    },
}


def run_local_etl(
    input_file: str,
    output_file: str,
    db_path: Optional[str] = None,
) -> Dict[str, Any]:
    input_path = Path(input_file).resolve()
    if not input_path.exists():
        raise FileNotFoundError(f"ETL input file does not exist: {input_path}")

    output_path = Path(output_file).resolve()

    owns_db = db_path is None
    if owns_db:
        fd, generated_path = tempfile.mkstemp(prefix="eap-starter-etl-", suffix=".db")
        os.close(fd)
        db_path = generated_path

    state_manager = StateManager(db_path=db_path)
    registry = ToolRegistry()
    registry.register("read_local_file", read_local_file, READ_FILE_SCHEMA)
    registry.register("transform_sales_jsonl", transform_sales_jsonl, TRANSFORM_SALES_SCHEMA)
    registry.register("write_local_file", write_local_file, WRITE_FILE_SCHEMA)
    executor = AsyncLocalExecutor(state_manager, registry)

    try:
        macro = BatchedMacroRequest(
            steps=[
                ToolCall(
                    step_id="read_input_jsonl",
                    tool_name="read_local_file",
                    arguments={"file_path": str(input_path)},
                ),
                ToolCall(
                    step_id="transform_payload",
                    tool_name="transform_sales_jsonl",
                    arguments={"raw_data": "$step:read_input_jsonl"},
                ),
                ToolCall(
                    step_id="write_output_json",
                    tool_name="write_local_file",
                    arguments={
                        "file_path": str(output_path),
                        "content": "$step:transform_payload",
                        "mode": "overwrite",
                        "create_directories": True,
                    },
                ),
            ]
        )
        result = asyncio.run(executor.execute_macro(macro))
        output_payload = json.loads(output_path.read_text(encoding="utf-8"))
        return {
            "input_file": str(input_path),
            "output_file": str(output_path),
            "metrics": output_payload,
            "run_id": result["metadata"]["execution_run_id"],
            "pointer_id": result["pointer_id"],
        }
    finally:
        if owns_db and db_path and os.path.exists(db_path):
            os.remove(db_path)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the local ETL starter pack on JSONL input.")
    parser.add_argument(
        "--input-file",
        default="docs/starter_packs/fixtures/local_etl_orders.jsonl",
        help="Path to source JSONL file.",
    )
    parser.add_argument(
        "--output-file",
        default="artifacts/starter_pack_local_etl/aggregates.json",
        help="Path for transformed JSON metrics output.",
    )
    parser.add_argument(
        "--db-path",
        default=None,
        help="Optional SQLite state DB path (temporary by default).",
    )
    args = parser.parse_args()
    payload = run_local_etl(
        input_file=args.input_file,
        output_file=args.output_file,
        db_path=args.db_path,
    )
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
