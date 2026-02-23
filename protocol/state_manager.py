# protocol/state_manager.py
import uuid
import sys
import sqlite3
import json
import os
from pathlib import Path
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from .models import (
    ConversationSession,
    ConversationTurn,
    ExecutionTraceEvent,
    MemoryStrategy,
    PointerResponse,
)
from .migrations import apply_sqlite_migrations
from .storage import PointerStoreBackend, SQLitePointerStore

class StateManager:
    """
    Manages state using a local SQLite database for persistence.
    Large tool outputs are stored on disk, and lightweight pointers are sent to the LLM.
    """
    def __init__(
        self,
        db_path: str = "agent_state.db",
        pointer_store: Optional[PointerStoreBackend] = None,
    ):
        self.db_path = db_path
        self.pointer_store = pointer_store or SQLitePointerStore(db_path=self.db_path)
        self._init_db()

    def _init_db(self):
        self.pointer_store.initialize()
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS execution_trace_events (
                    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT NOT NULL,
                    step_id TEXT NOT NULL,
                    tool_name TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    timestamp_utc TEXT NOT NULL,
                    attempt INTEGER NOT NULL,
                    resolved_arguments TEXT,
                    input_pointer_ids TEXT,
                    output_pointer_id TEXT,
                    duration_ms REAL,
                    retry_delay_seconds REAL,
                    error_payload TEXT
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_execution_trace_events_run_id ON execution_trace_events(run_id)"
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS execution_run_summaries (
                    run_id TEXT PRIMARY KEY,
                    started_at_utc TEXT NOT NULL,
                    completed_at_utc TEXT NOT NULL,
                    total_steps INTEGER NOT NULL,
                    succeeded_steps INTEGER NOT NULL,
                    failed_steps INTEGER NOT NULL,
                    total_duration_ms REAL NOT NULL,
                    final_pointer_id TEXT
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS conversation_sessions (
                    session_id TEXT PRIMARY KEY,
                    created_at_utc TEXT NOT NULL,
                    updated_at_utc TEXT NOT NULL,
                    memory_strategy TEXT NOT NULL,
                    window_turn_limit INTEGER,
                    summary_text TEXT,
                    metadata TEXT
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS conversation_turns (
                    turn_id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at_utc TEXT NOT NULL,
                    pointer_ids TEXT,
                    macro_run_id TEXT,
                    metadata TEXT
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_conversation_turns_session_id ON conversation_turns(session_id)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_conversation_sessions_updated_at ON conversation_sessions(updated_at_utc)"
            )
        apply_sqlite_migrations(self.db_path)

    @staticmethod
    def _now_utc_iso() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _parse_now_utc(now_utc: Optional[str] = None) -> datetime:
        if now_utc is None:
            return datetime.now(timezone.utc)
        parsed = datetime.fromisoformat(now_utc)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)

    def _generate_id(self) -> str:
        return f"ptr_{uuid.uuid4().hex[:8]}"

    def store_and_point(
        self,
        raw_data: Any,
        summary: str,
        metadata: dict = None,
        ttl_seconds: Optional[int] = None,
    ) -> dict:
        pointer_id = self._generate_id()
        meta = metadata or {}
        meta["size_bytes"] = sys.getsizeof(raw_data)

        if ttl_seconds is not None:
            if not isinstance(ttl_seconds, int) or isinstance(ttl_seconds, bool):
                raise ValueError("ttl_seconds must be an integer when provided.")
            if ttl_seconds <= 0:
                raise ValueError("ttl_seconds must be > 0 when provided.")

        created_at_utc = self._now_utc_iso()
        expires_at_utc = None
        if ttl_seconds is not None:
            expires_at_utc = (
                datetime.fromisoformat(created_at_utc) + timedelta(seconds=ttl_seconds)
            ).isoformat()

        meta["created_at_utc"] = created_at_utc
        meta["ttl_seconds"] = ttl_seconds
        meta["expires_at_utc"] = expires_at_utc

        self.pointer_store.store_pointer(
            pointer_id=pointer_id,
            raw_data=str(raw_data),
            summary=summary,
            metadata=meta,
            created_at_utc=created_at_utc,
            ttl_seconds=ttl_seconds,
            expires_at_utc=expires_at_utc,
        )

        return PointerResponse(
            pointer_id=pointer_id,
            summary=summary,
            metadata=meta
        ).model_dump()

    def retrieve(self, pointer_id: str) -> Any:
        return self.pointer_store.retrieve_pointer(pointer_id)

    def list_pointers(
        self,
        include_expired: bool = True,
        now_utc: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        return self.pointer_store.list_pointers(
            include_expired=include_expired,
            now_utc=now_utc,
            limit=limit,
        )

    def list_expired_pointers(
        self,
        now_utc: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        return self.pointer_store.list_expired_pointers(now_utc=now_utc, limit=limit)

    def delete_pointer(self, pointer_id: str) -> None:
        if not self.pointer_store.delete_pointer(pointer_id):
            raise KeyError(f"Pointer {pointer_id} not found in persistent storage.")

    def cleanup_expired_pointers(
        self,
        now_utc: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> Dict[str, Any]:
        return self.pointer_store.cleanup_expired_pointers(now_utc=now_utc, limit=limit)

    def append_trace_event(self, event: ExecutionTraceEvent) -> None:
        payload = event.model_dump(mode="json")
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO execution_trace_events (
                    run_id, step_id, tool_name, event_type, timestamp_utc, attempt,
                    resolved_arguments, input_pointer_ids, output_pointer_id, duration_ms,
                    retry_delay_seconds, error_payload
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    payload["run_id"],
                    payload["step_id"],
                    payload["tool_name"],
                    payload["event_type"],
                    payload["timestamp_utc"],
                    payload["attempt"],
                    json.dumps(payload["resolved_arguments"]) if payload["resolved_arguments"] is not None else None,
                    json.dumps(payload["input_pointer_ids"]) if payload["input_pointer_ids"] is not None else None,
                    payload["output_pointer_id"],
                    payload["duration_ms"],
                    payload["retry_delay_seconds"],
                    json.dumps(payload["error"]) if payload["error"] is not None else None,
                ),
            )

    def list_trace_events(self, run_id: str) -> List[ExecutionTraceEvent]:
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                """
                SELECT step_id, tool_name, event_type, timestamp_utc, attempt, resolved_arguments,
                       input_pointer_ids, output_pointer_id, duration_ms, retry_delay_seconds, error_payload
                FROM execution_trace_events
                WHERE run_id = ?
                ORDER BY event_id ASC
                """,
                (run_id,),
            ).fetchall()

        events: List[ExecutionTraceEvent] = []
        for row in rows:
            events.append(
                ExecutionTraceEvent(
                    run_id=run_id,
                    step_id=row[0],
                    tool_name=row[1],
                    event_type=row[2],
                    timestamp_utc=row[3],
                    attempt=row[4],
                    resolved_arguments=json.loads(row[5]) if row[5] else None,
                    input_pointer_ids=json.loads(row[6]) if row[6] else None,
                    output_pointer_id=row[7],
                    duration_ms=row[8],
                    retry_delay_seconds=row[9],
                    error=json.loads(row[10]) if row[10] else None,
                )
            )
        return events

    def store_execution_summary(
        self,
        run_id: str,
        started_at_utc: str,
        completed_at_utc: str,
        total_steps: int,
        succeeded_steps: int,
        failed_steps: int,
        total_duration_ms: float,
        final_pointer_id: Optional[str] = None,
    ) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO execution_run_summaries (
                    run_id, started_at_utc, completed_at_utc, total_steps,
                    succeeded_steps, failed_steps, total_duration_ms, final_pointer_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    started_at_utc,
                    completed_at_utc,
                    total_steps,
                    succeeded_steps,
                    failed_steps,
                    total_duration_ms,
                    final_pointer_id,
                ),
            )

    def get_execution_summary(self, run_id: str) -> Dict[str, Any]:
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                """
                SELECT started_at_utc, completed_at_utc, total_steps, succeeded_steps, failed_steps,
                       total_duration_ms, final_pointer_id
                FROM execution_run_summaries
                WHERE run_id = ?
                """,
                (run_id,),
            ).fetchone()

        if not row:
            raise KeyError(f"Execution summary for run {run_id} not found.")

        return {
            "run_id": run_id,
            "started_at_utc": row[0],
            "completed_at_utc": row[1],
            "total_steps": row[2],
            "succeeded_steps": row[3],
            "failed_steps": row[4],
            "total_duration_ms": row[5],
            "final_pointer_id": row[6],
        }

    def _generate_session_id(self) -> str:
        return f"sess_{uuid.uuid4().hex[:10]}"

    def _generate_turn_id(self) -> str:
        return f"turn_{uuid.uuid4().hex[:12]}"

    def create_session(
        self,
        session_id: Optional[str] = None,
        memory_strategy: MemoryStrategy = MemoryStrategy.FULL,
        window_turn_limit: Optional[int] = None,
        summary_text: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        created_session_id = session_id or self._generate_session_id()
        now_utc = self._now_utc_iso()
        session = ConversationSession(
            session_id=created_session_id,
            created_at_utc=now_utc,
            updated_at_utc=now_utc,
            memory_strategy=memory_strategy,
            window_turn_limit=window_turn_limit,
            summary_text=summary_text,
            metadata=metadata,
        )
        payload = session.model_dump(mode="json")
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO conversation_sessions (
                    session_id, created_at_utc, updated_at_utc, memory_strategy,
                    window_turn_limit, summary_text, metadata
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    payload["session_id"],
                    payload["created_at_utc"],
                    payload["updated_at_utc"],
                    payload["memory_strategy"],
                    payload["window_turn_limit"],
                    payload["summary_text"],
                    json.dumps(payload["metadata"]) if payload["metadata"] is not None else None,
                ),
            )
        return payload

    def get_session(self, session_id: str) -> Dict[str, Any]:
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                """
                SELECT created_at_utc, updated_at_utc, memory_strategy, window_turn_limit, summary_text, metadata
                FROM conversation_sessions
                WHERE session_id = ?
                """,
                (session_id,),
            ).fetchone()

        if not row:
            raise KeyError(f"Session {session_id} not found.")

        session = ConversationSession(
            session_id=session_id,
            created_at_utc=row[0],
            updated_at_utc=row[1],
            memory_strategy=row[2],
            window_turn_limit=row[3],
            summary_text=row[4],
            metadata=json.loads(row[5]) if row[5] else None,
        )
        return session.model_dump(mode="json")

    def list_sessions(self, limit: int = 50) -> List[Dict[str, Any]]:
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                """
                SELECT session_id, created_at_utc, updated_at_utc, memory_strategy, window_turn_limit, summary_text, metadata
                FROM conversation_sessions
                ORDER BY updated_at_utc DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()

        sessions: List[Dict[str, Any]] = []
        for row in rows:
            session = ConversationSession(
                session_id=row[0],
                created_at_utc=row[1],
                updated_at_utc=row[2],
                memory_strategy=row[3],
                window_turn_limit=row[4],
                summary_text=row[5],
                metadata=json.loads(row[6]) if row[6] else None,
            )
            sessions.append(session.model_dump(mode="json"))
        return sessions

    def delete_session(self, session_id: str) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("DELETE FROM conversation_turns WHERE session_id = ?", (session_id,))
            cursor = conn.execute("DELETE FROM conversation_sessions WHERE session_id = ?", (session_id,))

        if cursor.rowcount == 0:
            raise KeyError(f"Session {session_id} not found.")

    def append_turn(
        self,
        session_id: str,
        role: str,
        content: str,
        pointer_ids: Optional[List[str]] = None,
        macro_run_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        turn_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        # Ensure session exists before writing turn.
        self.get_session(session_id)

        created_turn_id = turn_id or self._generate_turn_id()
        now_utc = self._now_utc_iso()
        turn = ConversationTurn(
            turn_id=created_turn_id,
            session_id=session_id,
            role=role,
            content=content,
            created_at_utc=now_utc,
            pointer_ids=pointer_ids or [],
            macro_run_id=macro_run_id,
            metadata=metadata,
        )
        payload = turn.model_dump(mode="json")
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO conversation_turns (
                    turn_id, session_id, role, content, created_at_utc, pointer_ids, macro_run_id, metadata
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    payload["turn_id"],
                    payload["session_id"],
                    payload["role"],
                    payload["content"],
                    payload["created_at_utc"],
                    json.dumps(payload["pointer_ids"]),
                    payload["macro_run_id"],
                    json.dumps(payload["metadata"]) if payload["metadata"] is not None else None,
                ),
            )
            conn.execute(
                """
                UPDATE conversation_sessions
                SET updated_at_utc = ?
                WHERE session_id = ?
                """,
                (now_utc, session_id),
            )
        self.apply_memory_policy(session_id=session_id)
        return payload

    def list_turns(self, session_id: str, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        # Validate session exists for clear caller errors.
        self.get_session(session_id)

        query = """
            SELECT turn_id, role, content, created_at_utc, pointer_ids, macro_run_id, metadata
            FROM conversation_turns
            WHERE session_id = ?
            ORDER BY created_at_utc ASC
        """
        params: tuple = (session_id,)
        if limit is not None:
            query += " LIMIT ?"
            params = (session_id, limit)

        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(query, params).fetchall()

        turns: List[Dict[str, Any]] = []
        for row in rows:
            turn = ConversationTurn(
                turn_id=row[0],
                session_id=session_id,
                role=row[1],
                content=row[2],
                created_at_utc=row[3],
                pointer_ids=json.loads(row[4]) if row[4] else [],
                macro_run_id=row[5],
                metadata=json.loads(row[6]) if row[6] else None,
            )
            turns.append(turn.model_dump(mode="json"))
        return turns

    def apply_memory_policy(
        self,
        session_id: str,
        keep_recent_turns: int = 4,
        default_window_turn_limit: int = 8,
        max_summary_chars: int = 2000,
    ) -> Dict[str, Any]:
        session = self.get_session(session_id)
        turns = self.list_turns(session_id)
        strategy = session["memory_strategy"]
        deleted_count = 0
        summary_updated = False
        new_summary_text = session.get("summary_text")

        if strategy == MemoryStrategy.WINDOW.value:
            window_limit = session.get("window_turn_limit") or default_window_turn_limit
            overflow = max(0, len(turns) - window_limit)
            if overflow > 0:
                to_delete = [turn["turn_id"] for turn in turns[:overflow]]
                with sqlite3.connect(self.db_path) as conn:
                    conn.executemany(
                        "DELETE FROM conversation_turns WHERE turn_id = ?",
                        [(turn_id,) for turn_id in to_delete],
                    )
                    conn.execute(
                        "UPDATE conversation_sessions SET updated_at_utc = ? WHERE session_id = ?",
                        (self._now_utc_iso(), session_id),
                    )
                deleted_count = overflow

        if strategy == MemoryStrategy.SUMMARY.value:
            overflow = max(0, len(turns) - keep_recent_turns)
            if overflow > 0:
                old_turns = turns[:overflow]
                to_keep = turns[overflow:]
                prior_summary = session.get("summary_text") or ""

                summary_lines = []
                for turn in old_turns:
                    clipped = turn["content"][:180]
                    line = f"{turn['role']}: {clipped}"
                    pointers = turn.get("pointer_ids") or []
                    if pointers:
                        line += f" | pointers: {', '.join(pointers)}"
                    summary_lines.append(line)

                merged_summary = "\n".join(
                    item for item in [prior_summary, "\n".join(summary_lines)] if item
                ).strip()
                if len(merged_summary) > max_summary_chars:
                    merged_summary = merged_summary[-max_summary_chars:]

                to_delete = [turn["turn_id"] for turn in old_turns]
                with sqlite3.connect(self.db_path) as conn:
                    conn.executemany(
                        "DELETE FROM conversation_turns WHERE turn_id = ?",
                        [(turn_id,) for turn_id in to_delete],
                    )
                    conn.execute(
                        """
                        UPDATE conversation_sessions
                        SET summary_text = ?, updated_at_utc = ?
                        WHERE session_id = ?
                        """,
                        (merged_summary, self._now_utc_iso(), session_id),
                    )
                deleted_count = len(old_turns)
                summary_updated = True
                new_summary_text = merged_summary
                turns = to_keep

        return {
            "session_id": session_id,
            "strategy": strategy,
            "deleted_turn_count": deleted_count,
            "remaining_turn_count": len(turns) - deleted_count if strategy == MemoryStrategy.WINDOW.value else len(turns),
            "summary_updated": summary_updated,
            "summary_text": new_summary_text,
        }

    def clear_all(self):
        if os.path.exists(self.db_path):
            os.remove(self.db_path)
            self._init_db()

    def collect_operational_metrics(self, now_utc: Optional[str] = None) -> Dict[str, Any]:
        snapshot_now = self._parse_now_utc(now_utc).isoformat()

        total_pointers = len(self.list_pointers(include_expired=True, now_utc=snapshot_now))
        active_pointers = len(self.list_pointers(include_expired=False, now_utc=snapshot_now))
        expired_pointers = max(0, total_pointers - active_pointers)

        with sqlite3.connect(self.db_path) as conn:
            run_row = conn.execute(
                """
                SELECT
                    COUNT(*) AS run_count,
                    COALESCE(SUM(total_steps), 0) AS total_steps,
                    COALESCE(SUM(succeeded_steps), 0) AS succeeded_steps,
                    COALESCE(SUM(failed_steps), 0) AS failed_steps,
                    COALESCE(AVG(total_duration_ms), 0.0) AS avg_duration_ms
                FROM execution_run_summaries
                """
            ).fetchone()
            failed_run_count = conn.execute(
                "SELECT COUNT(*) FROM execution_run_summaries WHERE failed_steps > 0"
            ).fetchone()[0]

            event_rows = conn.execute(
                """
                SELECT event_type, COUNT(*)
                FROM execution_trace_events
                GROUP BY event_type
                """
            ).fetchall()
            trace_event_total = conn.execute("SELECT COUNT(*) FROM execution_trace_events").fetchone()[0]

            session_count = conn.execute("SELECT COUNT(*) FROM conversation_sessions").fetchone()[0]
            turn_count = conn.execute("SELECT COUNT(*) FROM conversation_turns").fetchone()[0]

        return {
            "snapshot_utc": snapshot_now,
            "db_path": self.db_path,
            "pointer_store": {
                "total_pointers": total_pointers,
                "active_pointers": active_pointers,
                "expired_pointers": expired_pointers,
            },
            "execution": {
                "run_count": int(run_row[0]),
                "failed_run_count": int(failed_run_count),
                "total_steps": int(run_row[1]),
                "succeeded_steps": int(run_row[2]),
                "failed_steps": int(run_row[3]),
                "avg_duration_ms": float(run_row[4]),
                "trace_event_total": int(trace_event_total),
                "trace_events_by_type": {row[0]: int(row[1]) for row in event_rows},
            },
            "conversation": {
                "session_count": int(session_count),
                "turn_count": int(turn_count),
            },
        }

    def export_operational_metrics(
        self,
        output_path: str,
        now_utc: Optional[str] = None,
    ) -> Dict[str, Any]:
        metrics = self.collect_operational_metrics(now_utc=now_utc)
        output = Path(output_path)
        if output.parent and str(output.parent) != ".":
            output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(metrics, indent=2, sort_keys=True), encoding="utf-8")
        return {
            "output_path": str(output.resolve()),
            "snapshot_utc": metrics["snapshot_utc"],
        }
