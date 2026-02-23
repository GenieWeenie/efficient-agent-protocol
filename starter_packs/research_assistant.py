from __future__ import annotations

import argparse
import asyncio
import json
import os
import tempfile
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, Optional

from eap.environment import AsyncLocalExecutor, ToolRegistry
from eap.environment.tools import ANALYZE_SCHEMA, SCRAPE_SCHEMA, analyze_data, scrape_url
from eap.protocol import BatchedMacroRequest, StateManager, ToolCall


class _SilentHandler(SimpleHTTPRequestHandler):
    def log_message(self, format: str, *args) -> None:  # noqa: A003
        return


def run_research_assistant(
    question: str,
    html_file: str,
    db_path: Optional[str] = None,
) -> Dict[str, Any]:
    html_path = Path(html_file).resolve()
    if not html_path.exists():
        raise FileNotFoundError(f"Research source file does not exist: {html_path}")

    owns_db = db_path is None
    if owns_db:
        fd, generated_path = tempfile.mkstemp(prefix="eap-starter-research-", suffix=".db")
        os.close(fd)
        db_path = generated_path

    source_dir = str(html_path.parent)
    handler_cls = partial(_SilentHandler, directory=source_dir)
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler_cls)
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()

    source_url = f"http://127.0.0.1:{server.server_address[1]}/{html_path.name}"
    state_manager = StateManager(db_path=db_path)
    registry = ToolRegistry()
    registry.register("scrape_url", scrape_url, SCRAPE_SCHEMA)
    registry.register("analyze_data", analyze_data, ANALYZE_SCHEMA)
    executor = AsyncLocalExecutor(state_manager, registry)

    try:
        macro = BatchedMacroRequest(
            steps=[
                ToolCall(
                    step_id="collect_source_text",
                    tool_name="scrape_url",
                    arguments={"url": source_url},
                ),
                ToolCall(
                    step_id="answer_question",
                    tool_name="analyze_data",
                    arguments={
                        "raw_data": "$step:collect_source_text",
                        "focus": question,
                    },
                ),
            ]
        )
        result = asyncio.run(executor.execute_macro(macro))
        answer = state_manager.retrieve(result["pointer_id"])
        return {
            "question": question,
            "source_url": source_url,
            "answer": answer,
            "run_id": result["metadata"]["execution_run_id"],
            "pointer_id": result["pointer_id"],
        }
    finally:
        server.shutdown()
        server.server_close()
        server_thread.join(timeout=1.0)
        if owns_db and db_path and os.path.exists(db_path):
            os.remove(db_path)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run the research-assistant starter pack over a local HTML source."
    )
    parser.add_argument(
        "--question",
        required=True,
        help="Research question to answer from the source page.",
    )
    parser.add_argument(
        "--html-file",
        default="docs/starter_packs/fixtures/research_source.html",
        help="Path to local HTML file used as the source corpus.",
    )
    parser.add_argument(
        "--db-path",
        default=None,
        help="Optional SQLite state DB path (temporary by default).",
    )
    args = parser.parse_args()
    payload = run_research_assistant(
        question=args.question,
        html_file=args.html_file,
        db_path=args.db_path,
    )
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
