#!/usr/bin/env python3
from __future__ import annotations

import argparse
import html
import sqlite3
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import List, Sequence, Tuple
from urllib.parse import urlparse


def _now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _fetch_count(conn: sqlite3.Connection, query: str) -> int:
    row = conn.execute(query).fetchone()
    if not row:
        return 0
    return int(row[0])


def _load_rows(conn: sqlite3.Connection, query: str, limit: int) -> List[Tuple]:
    return list(conn.execute(query, (limit,)).fetchall())


def _format_error_page(message: str) -> str:
    escaped = html.escape(message)
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta http-equiv="refresh" content="10" />
  <title>EAP Operator UI</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; margin: 2rem; }}
    .error {{ background: #fff4f4; border: 1px solid #e63946; color: #4a1015; padding: 1rem; border-radius: 0.5rem; }}
  </style>
</head>
<body>
  <h1>EAP Operator UI</h1>
  <p>Last refreshed (UTC): {html.escape(_now_utc())}</p>
  <div class="error">{escaped}</div>
</body>
</html>"""


def _render_table(headers: Sequence[str], rows: Sequence[Sequence[object]]) -> str:
    header_html = "".join(f"<th>{html.escape(column)}</th>" for column in headers)
    body_html = "".join(
        "<tr>"
        + "".join(f"<td>{html.escape('' if value is None else str(value))}</td>" for value in row)
        + "</tr>"
        for row in rows
    )
    return f"<table><thead><tr>{header_html}</tr></thead><tbody>{body_html}</tbody></table>"


def _render_dashboard(db_path: Path, run_limit: int, pointer_limit: int) -> str:
    if not db_path.exists():
        return _format_error_page(f"State DB not found yet: {db_path}")

    try:
        with sqlite3.connect(db_path) as conn:
            total_runs = _fetch_count(conn, "SELECT COUNT(*) FROM execution_run_summaries")
            total_pointers = _fetch_count(conn, "SELECT COUNT(*) FROM state_store")

            runs = _load_rows(
                conn,
                """
                SELECT run_id, completed_at_utc, total_steps, succeeded_steps, failed_steps, final_pointer_id
                FROM execution_run_summaries
                ORDER BY completed_at_utc DESC
                LIMIT ?
                """,
                run_limit,
            )
            pointers = _load_rows(
                conn,
                """
                SELECT pointer_id, summary, created_at_utc, expires_at_utc
                FROM state_store
                ORDER BY created_at_utc DESC
                LIMIT ?
                """,
                pointer_limit,
            )
    except sqlite3.DatabaseError as exc:
        return _format_error_page(f"Unable to read state DB: {exc}")

    runs_table = _render_table(
        ("run_id", "completed_at_utc", "total_steps", "succeeded_steps", "failed_steps", "final_pointer_id"),
        runs,
    )
    pointers_table = _render_table(
        ("pointer_id", "summary", "created_at_utc", "expires_at_utc"),
        pointers,
    )

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta http-equiv="refresh" content="10" />
  <title>EAP Operator UI</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; margin: 2rem; color: #111; }}
    h1, h2 {{ margin-bottom: 0.4rem; }}
    .meta {{ color: #555; margin-top: 0; }}
    .stats {{ display: flex; gap: 1rem; margin: 1rem 0 2rem 0; }}
    .card {{ border: 1px solid #ccc; border-radius: 0.5rem; padding: 0.8rem 1rem; min-width: 10rem; }}
    .card-value {{ font-size: 1.4rem; font-weight: 700; }}
    table {{ width: 100%; border-collapse: collapse; margin-bottom: 2rem; }}
    th, td {{ border: 1px solid #ddd; padding: 0.5rem; text-align: left; vertical-align: top; }}
    th {{ background: #f7f7f7; }}
    code {{ background: #f4f4f4; padding: 0.1rem 0.3rem; border-radius: 0.2rem; }}
  </style>
</head>
<body>
  <h1>EAP Operator UI</h1>
  <p class="meta">State DB: <code>{html.escape(str(db_path))}</code> | Last refreshed (UTC): {html.escape(_now_utc())}</p>
  <div class="stats">
    <div class="card">
      <div>Total runs</div>
      <div class="card-value">{total_runs}</div>
    </div>
    <div class="card">
      <div>Total pointers</div>
      <div class="card-value">{total_pointers}</div>
    </div>
  </div>
  <h2>Recent Runs</h2>
  {runs_table}
  <h2>Recent Pointers</h2>
  {pointers_table}
</body>
</html>"""


class _OperatorUIRequestHandler(BaseHTTPRequestHandler):
    server: "_OperatorUIHTTPServer"

    def do_GET(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        if path == "/healthz":
            self._send(200, "text/plain; charset=utf-8", b"ok\n")
            return
        if path != "/":
            self._send(404, "text/plain; charset=utf-8", b"not found\n")
            return

        html_page = _render_dashboard(
            db_path=self.server.db_path,
            run_limit=self.server.run_limit,
            pointer_limit=self.server.pointer_limit,
        )
        self._send(200, "text/html; charset=utf-8", html_page.encode("utf-8"))

    def log_message(self, format: str, *args) -> None:  # noqa: A003
        return

    def _send(self, status_code: int, content_type: str, payload: bytes) -> None:
        self.send_response(status_code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


class _OperatorUIHTTPServer(ThreadingHTTPServer):
    def __init__(
        self,
        server_address: Tuple[str, int],
        db_path: Path,
        run_limit: int,
        pointer_limit: int,
    ) -> None:
        super().__init__(server_address, _OperatorUIRequestHandler)
        self.db_path = db_path
        self.run_limit = run_limit
        self.pointer_limit = pointer_limit


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run EAP operator UI (read-only).")
    parser.add_argument("--host", default="0.0.0.0", help="Bind host (default: 0.0.0.0).")
    parser.add_argument("--port", type=int, default=8501, help="Bind port (default: 8501).")
    parser.add_argument("--db-path", default="agent_state.db", help="State DB path.")
    parser.add_argument(
        "--run-limit",
        type=int,
        default=20,
        help="Max number of runs shown in table (default: 20).",
    )
    parser.add_argument(
        "--pointer-limit",
        type=int,
        default=20,
        help="Max number of pointers shown in table (default: 20).",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    if args.port <= 0 or args.port > 65535:
        print("[operator-ui:error] --port must be between 1 and 65535.")
        return 1
    if args.run_limit <= 0 or args.pointer_limit <= 0:
        print("[operator-ui:error] --run-limit and --pointer-limit must be > 0.")
        return 1

    db_path = Path(args.db_path).resolve()
    server = _OperatorUIHTTPServer(
        server_address=(args.host, args.port),
        db_path=db_path,
        run_limit=args.run_limit,
        pointer_limit=args.pointer_limit,
    )
    print("[operator-ui] started.")
    print(f"[operator-ui] bind={args.host}:{args.port}")
    print(f"[operator-ui] db_path={db_path}")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.shutdown()
        server.server_close()
        print("[operator-ui] stopped.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
