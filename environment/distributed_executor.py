import json
import sqlite3
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from eap.protocol import BatchedMacroRequest, RetryPolicy, StateManager, ToolErrorPayload
from environment.tool_registry import ToolRegistry


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _now_utc_iso() -> str:
    return _now_utc().isoformat()


def _as_utc_iso(value: Optional[str]) -> str:
    if value is None:
        return _now_utc_iso()
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).isoformat()


class DistributedCoordinator:
    """SQLite-backed coordinator for distributed worker leases and step state."""

    def __init__(
        self,
        state_manager: StateManager,
        registry: ToolRegistry,
        db_path: Optional[str] = None,
        lease_ttl_seconds: int = 30,
    ) -> None:
        self.state_manager = state_manager
        self.registry = registry
        self.db_path = db_path or state_manager.db_path
        self.lease_ttl_seconds = lease_ttl_seconds
        self._init_tables()

    def _init_tables(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS distributed_steps (
                    run_id TEXT NOT NULL,
                    step_id TEXT NOT NULL,
                    tool_name TEXT NOT NULL,
                    arguments_json TEXT NOT NULL,
                    depends_on_json TEXT NOT NULL,
                    status TEXT NOT NULL,
                    attempt INTEGER NOT NULL,
                    max_attempts INTEGER NOT NULL,
                    next_attempt_at_utc TEXT,
                    output_pointer_id TEXT,
                    last_error_json TEXT,
                    updated_at_utc TEXT NOT NULL,
                    PRIMARY KEY (run_id, step_id)
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_distributed_steps_run_status ON distributed_steps(run_id, status)"
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS distributed_leases (
                    lease_id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL,
                    step_id TEXT NOT NULL,
                    worker_id TEXT NOT NULL,
                    attempt INTEGER NOT NULL,
                    issued_at_utc TEXT NOT NULL,
                    heartbeat_at_utc TEXT NOT NULL,
                    expires_at_utc TEXT NOT NULL,
                    status TEXT NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_distributed_leases_status ON distributed_leases(status, expires_at_utc)"
            )

    @staticmethod
    def _extract_dependencies(arguments: Dict[str, Any]) -> List[str]:
        deps = set()
        for value in arguments.values():
            if isinstance(value, str) and value.startswith("$step:"):
                dep_step_id = value.replace("$step:", "").split(".", 1)[0]
                if dep_step_id:
                    deps.add(dep_step_id)
        return sorted(deps)

    @staticmethod
    def _resolve_runtime_arguments(
        arguments: Dict[str, Any],
        output_pointer_by_step: Dict[str, str],
        state_manager: StateManager,
    ) -> Dict[str, Any]:
        resolved = {}
        for key, value in arguments.items():
            if isinstance(value, str) and value.startswith("$step:"):
                dep_step_id = value.replace("$step:", "").split(".", 1)[0]
                pointer_id = output_pointer_by_step.get(dep_step_id)
                if not pointer_id:
                    raise KeyError(f"Missing dependency pointer for step '{dep_step_id}'.")
                resolved[key] = state_manager.retrieve(pointer_id)
            else:
                resolved[key] = value
        return resolved

    def enqueue_macro(self, macro: BatchedMacroRequest, run_id: Optional[str] = None) -> str:
        run_id = run_id or f"run_dist_{uuid.uuid4().hex[:10]}"
        max_attempts = (macro.retry_policy or RetryPolicy()).max_attempts
        now_iso = _now_utc_iso()

        with sqlite3.connect(self.db_path) as conn:
            for step in macro.steps:
                depends_on = self._extract_dependencies(step.arguments)
                conn.execute(
                    """
                    INSERT OR REPLACE INTO distributed_steps (
                        run_id, step_id, tool_name, arguments_json, depends_on_json, status,
                        attempt, max_attempts, next_attempt_at_utc, output_pointer_id, last_error_json, updated_at_utc
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        run_id,
                        step.step_id,
                        step.tool_name,
                        json.dumps(step.arguments),
                        json.dumps(depends_on),
                        "queued",
                        0,
                        max_attempts,
                        now_iso,
                        None,
                        None,
                        now_iso,
                    ),
                )
        return run_id

    def _expire_stale_leases(self, now_iso: str) -> None:
        with sqlite3.connect(self.db_path) as conn:
            expired_rows = conn.execute(
                """
                SELECT lease_id, run_id, step_id
                FROM distributed_leases
                WHERE status = 'active' AND expires_at_utc <= ?
                """,
                (now_iso,),
            ).fetchall()

            for lease_id, run_id, step_id in expired_rows:
                conn.execute(
                    "UPDATE distributed_leases SET status = 'expired' WHERE lease_id = ?",
                    (lease_id,),
                )
                conn.execute(
                    """
                    UPDATE distributed_steps
                    SET status = 'queued', next_attempt_at_utc = ?, updated_at_utc = ?
                    WHERE run_id = ? AND step_id = ? AND status = 'started'
                    """,
                    (now_iso, now_iso, run_id, step_id),
                )

    def _completed_pointer_map(self, run_id: str) -> Dict[str, str]:
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                """
                SELECT step_id, output_pointer_id
                FROM distributed_steps
                WHERE run_id = ? AND status = 'completed'
                """,
                (run_id,),
            ).fetchall()
        return {row[0]: row[1] for row in rows if row[1]}

    def claim_work(self, worker_id: str, capacity: int = 1, now_utc: Optional[str] = None) -> List[Dict[str, Any]]:
        if capacity <= 0:
            return []

        now_iso = _as_utc_iso(now_utc)
        self._expire_stale_leases(now_iso)
        claims: List[Dict[str, Any]] = []

        with sqlite3.connect(self.db_path) as conn:
            queued_rows = conn.execute(
                """
                SELECT run_id, step_id, tool_name, arguments_json, depends_on_json, attempt, max_attempts, next_attempt_at_utc
                FROM distributed_steps
                WHERE status = 'queued'
                ORDER BY next_attempt_at_utc ASC, step_id ASC
                """,
            ).fetchall()

            for row in queued_rows:
                if len(claims) >= capacity:
                    break

                run_id, step_id, tool_name, arguments_json, depends_on_json, attempt, _, next_attempt_at = row
                if next_attempt_at and next_attempt_at > now_iso:
                    continue
                depends_on = json.loads(depends_on_json) if depends_on_json else []
                completed = self._completed_pointer_map(run_id)
                if any(dep not in completed for dep in depends_on):
                    continue

                next_attempt = int(attempt) + 1
                lease_id = f"lease_{uuid.uuid4().hex[:12]}"
                expires_at = (_now_utc() + timedelta(seconds=self.lease_ttl_seconds)).isoformat()
                conn.execute(
                    """
                    INSERT INTO distributed_leases (
                        lease_id, run_id, step_id, worker_id, attempt, issued_at_utc, heartbeat_at_utc, expires_at_utc, status
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        lease_id,
                        run_id,
                        step_id,
                        worker_id,
                        next_attempt,
                        now_iso,
                        now_iso,
                        expires_at,
                        "active",
                    ),
                )
                conn.execute(
                    """
                    UPDATE distributed_steps
                    SET status = 'started', attempt = ?, updated_at_utc = ?
                    WHERE run_id = ? AND step_id = ?
                    """,
                    (next_attempt, now_iso, run_id, step_id),
                )
                claims.append(
                    {
                        "lease_id": lease_id,
                        "run_id": run_id,
                        "step_id": step_id,
                        "tool_name": tool_name,
                        "arguments": json.loads(arguments_json),
                        "attempt": next_attempt,
                        "expires_at_utc": expires_at,
                    }
                )
        return claims

    def heartbeat(self, lease_id: str, worker_id: str, now_utc: Optional[str] = None) -> bool:
        now_iso = _as_utc_iso(now_utc)
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                """
                SELECT expires_at_utc, worker_id, status
                FROM distributed_leases
                WHERE lease_id = ?
                """,
                (lease_id,),
            ).fetchone()
            if not row:
                return False
            expires_at, owner_worker_id, status = row
            if owner_worker_id != worker_id or status != "active" or expires_at <= now_iso:
                return False
            new_expiry = (_now_utc() + timedelta(seconds=self.lease_ttl_seconds)).isoformat()
            conn.execute(
                """
                UPDATE distributed_leases
                SET heartbeat_at_utc = ?, expires_at_utc = ?
                WHERE lease_id = ?
                """,
                (now_iso, new_expiry, lease_id),
            )
            return True

    def complete_lease(self, lease_id: str, worker_id: str, output_pointer_id: str) -> bool:
        now_iso = _now_utc_iso()
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                """
                SELECT run_id, step_id, worker_id, status
                FROM distributed_leases
                WHERE lease_id = ?
                """,
                (lease_id,),
            ).fetchone()
            if not row:
                return False
            run_id, step_id, owner_worker_id, status = row
            if owner_worker_id != worker_id or status != "active":
                return False
            conn.execute(
                "UPDATE distributed_leases SET status = 'completed' WHERE lease_id = ?",
                (lease_id,),
            )
            conn.execute(
                """
                UPDATE distributed_steps
                SET status = 'completed', output_pointer_id = ?, updated_at_utc = ?
                WHERE run_id = ? AND step_id = ?
                """,
                (output_pointer_id, now_iso, run_id, step_id),
            )
            return True

    def fail_lease(
        self,
        lease_id: str,
        worker_id: str,
        error: ToolErrorPayload,
        retry_delay_seconds: float = 0.0,
    ) -> bool:
        now = _now_utc()
        now_iso = now.isoformat()
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                """
                SELECT run_id, step_id, worker_id, status
                FROM distributed_leases
                WHERE lease_id = ?
                """,
                (lease_id,),
            ).fetchone()
            if not row:
                return False
            run_id, step_id, owner_worker_id, status = row
            if owner_worker_id != worker_id or status != "active":
                return False

            step_row = conn.execute(
                """
                SELECT attempt, max_attempts
                FROM distributed_steps
                WHERE run_id = ? AND step_id = ?
                """,
                (run_id, step_id),
            ).fetchone()
            if not step_row:
                return False
            attempt, max_attempts = step_row
            can_retry = int(attempt) < int(max_attempts)
            next_status = "queued" if can_retry else "failed"
            next_attempt_at = (
                (now + timedelta(seconds=max(0.0, retry_delay_seconds))).isoformat()
                if can_retry
                else None
            )

            conn.execute("UPDATE distributed_leases SET status = 'failed' WHERE lease_id = ?", (lease_id,))
            conn.execute(
                """
                UPDATE distributed_steps
                SET status = ?, next_attempt_at_utc = ?, last_error_json = ?, updated_at_utc = ?
                WHERE run_id = ? AND step_id = ?
                """,
                (
                    next_status,
                    next_attempt_at,
                    json.dumps(error.model_dump(mode="json")),
                    now_iso,
                    run_id,
                    step_id,
                ),
            )
            return True

    def list_run_steps(self, run_id: str) -> List[Dict[str, Any]]:
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                """
                SELECT step_id, status, attempt, max_attempts, output_pointer_id, last_error_json, updated_at_utc
                FROM distributed_steps
                WHERE run_id = ?
                ORDER BY step_id ASC
                """,
                (run_id,),
            ).fetchall()
        result = []
        for row in rows:
            result.append(
                {
                    "step_id": row[0],
                    "status": row[1],
                    "attempt": row[2],
                    "max_attempts": row[3],
                    "output_pointer_id": row[4],
                    "last_error": json.loads(row[5]) if row[5] else None,
                    "updated_at_utc": row[6],
                }
            )
        return result

    def execute_worker_loop(
        self,
        worker_id: str,
        poll_interval_seconds: float = 0.1,
        max_iterations: int = 100,
    ) -> None:
        iterations = 0
        while iterations < max_iterations:
            iterations += 1
            claimed = self.claim_work(worker_id=worker_id, capacity=1)
            if not claimed:
                time.sleep(poll_interval_seconds)
                continue

            task = claimed[0]
            run_id = task["run_id"]
            step_id = task["step_id"]
            lease_id = task["lease_id"]
            arguments = task["arguments"]
            tool_name = task["tool_name"]

            completed_map = self._completed_pointer_map(run_id)
            try:
                resolved_args = self._resolve_runtime_arguments(
                    arguments=arguments,
                    output_pointer_by_step=completed_map,
                    state_manager=self.state_manager,
                )
                tool = self.registry.get_tool(tool_name)
                result = tool(**resolved_args)
                pointer = self.state_manager.store_and_point(
                    raw_data=result,
                    summary=f"Distributed step '{step_id}' completed.",
                    metadata={"run_id": run_id, "step_id": step_id, "worker_id": worker_id},
                )
                self.complete_lease(
                    lease_id=lease_id,
                    worker_id=worker_id,
                    output_pointer_id=pointer["pointer_id"],
                )
            except Exception as exc:
                error = ToolErrorPayload(
                    error_type="tool_execution_error",
                    message=str(exc),
                    step_id=step_id,
                    tool_name=tool_name,
                    details={"run_id": run_id, "worker_id": worker_id},
                )
                self.fail_lease(
                    lease_id=lease_id,
                    worker_id=worker_id,
                    error=error,
                )
