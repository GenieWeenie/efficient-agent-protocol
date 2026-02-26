from __future__ import annotations

import math
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from threading import Lock
from typing import Callable, Deque, Dict, Optional, Tuple

RUNTIME_OPERATION_MACRO_EXECUTE = "macro_execute"
RUNTIME_OPERATION_RUN_RESUME = "run_resume"
RUNTIME_OPERATION_RUN_READ = "run_read"
RUNTIME_OPERATION_POINTER_SUMMARY = "pointer_summary"

RUNTIME_OPERATIONS = {
    RUNTIME_OPERATION_MACRO_EXECUTE,
    RUNTIME_OPERATION_RUN_RESUME,
    RUNTIME_OPERATION_RUN_READ,
    RUNTIME_OPERATION_POINTER_SUMMARY,
}


@dataclass(frozen=True)
class RateLimitRule:
    max_requests: int
    window_seconds: float

    def validate(self, *, operation: str) -> None:
        if self.max_requests <= 0:
            raise ValueError(f"rate limit for '{operation}' must have max_requests > 0.")
        if self.window_seconds <= 0:
            raise ValueError(f"rate limit for '{operation}' must have window_seconds > 0.")


@dataclass(frozen=True)
class ConcurrencyLimits:
    global_inflight: int
    execute_inflight: int
    resume_inflight: int
    per_run_resume_inflight: int

    def validate(self) -> None:
        if self.global_inflight <= 0:
            raise ValueError("concurrency global_inflight must be > 0.")
        if self.execute_inflight <= 0:
            raise ValueError("concurrency execute_inflight must be > 0.")
        if self.resume_inflight <= 0:
            raise ValueError("concurrency resume_inflight must be > 0.")
        if self.per_run_resume_inflight <= 0:
            raise ValueError("concurrency per_run_resume_inflight must be > 0.")


@dataclass(frozen=True)
class RateLimitDecision:
    allowed: bool
    operation: str
    actor_id: str
    limit: int
    window_seconds: float
    remaining: int
    retry_after_seconds: float


@dataclass(frozen=True)
class ConcurrencyDecision:
    allowed: bool
    operation: str
    run_id: Optional[str]
    limit_type: Optional[str]
    limit: int
    current_inflight: int


@dataclass(frozen=True)
class ConcurrencyToken:
    operation: str
    run_id: Optional[str]


DEFAULT_RATE_LIMIT_RULES: Dict[str, RateLimitRule] = {
    RUNTIME_OPERATION_MACRO_EXECUTE: RateLimitRule(max_requests=60, window_seconds=60.0),
    RUNTIME_OPERATION_RUN_RESUME: RateLimitRule(max_requests=60, window_seconds=60.0),
    RUNTIME_OPERATION_RUN_READ: RateLimitRule(max_requests=240, window_seconds=60.0),
    RUNTIME_OPERATION_POINTER_SUMMARY: RateLimitRule(max_requests=240, window_seconds=60.0),
}

DEFAULT_CONCURRENCY_LIMITS = ConcurrencyLimits(
    global_inflight=12,
    execute_inflight=6,
    resume_inflight=6,
    per_run_resume_inflight=1,
)


def _coerce_int(*, value: object, field: str, operation: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"Invalid integer for '{field}' in '{operation}'.")
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if not value.is_integer():
            raise ValueError(f"Invalid integer for '{field}' in '{operation}'.")
        return int(value)
    if isinstance(value, str):
        try:
            return int(value.strip())
        except ValueError as exc:
            raise ValueError(f"Invalid integer for '{field}' in '{operation}'.") from exc
    raise ValueError(f"Invalid integer for '{field}' in '{operation}'.")


def _coerce_float(*, value: object, field: str, operation: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"Invalid float for '{field}' in '{operation}'.")
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip())
        except ValueError as exc:
            raise ValueError(f"Invalid float for '{field}' in '{operation}'.") from exc
    raise ValueError(f"Invalid float for '{field}' in '{operation}'.")


def normalize_rate_limit_rules(raw_rules: Optional[Dict[str, Dict[str, object]]]) -> Dict[str, RateLimitRule]:
    if not raw_rules:
        return dict(DEFAULT_RATE_LIMIT_RULES)

    normalized: Dict[str, RateLimitRule] = dict(DEFAULT_RATE_LIMIT_RULES)
    for operation, raw_rule in raw_rules.items():
        op = str(operation).strip().lower()
        if op not in RUNTIME_OPERATIONS:
            raise ValueError(f"Unsupported rate limit operation '{operation}'.")
        if not isinstance(raw_rule, dict):
            raise ValueError(f"Rate limit for '{operation}' must be an object.")
        max_requests = _coerce_int(
            value=raw_rule.get("max_requests", 0),
            field="max_requests",
            operation=op,
        )
        window_seconds = _coerce_float(
            value=raw_rule.get("window_seconds", 0),
            field="window_seconds",
            operation=op,
        )
        rule = RateLimitRule(max_requests=max_requests, window_seconds=window_seconds)
        rule.validate(operation=op)
        normalized[op] = rule
    return normalized


def normalize_concurrency_limits(raw_limits: Optional[Dict[str, object]]) -> ConcurrencyLimits:
    if not raw_limits:
        return DEFAULT_CONCURRENCY_LIMITS
    if not isinstance(raw_limits, dict):
        raise ValueError("concurrency config must be an object.")

    limits = ConcurrencyLimits(
        global_inflight=_coerce_int(
            value=raw_limits.get("global_inflight", DEFAULT_CONCURRENCY_LIMITS.global_inflight),
            field="global_inflight",
            operation="concurrency",
        ),
        execute_inflight=_coerce_int(
            value=raw_limits.get("execute_inflight", DEFAULT_CONCURRENCY_LIMITS.execute_inflight),
            field="execute_inflight",
            operation="concurrency",
        ),
        resume_inflight=_coerce_int(
            value=raw_limits.get("resume_inflight", DEFAULT_CONCURRENCY_LIMITS.resume_inflight),
            field="resume_inflight",
            operation="concurrency",
        ),
        per_run_resume_inflight=_coerce_int(
            value=raw_limits.get(
                "per_run_resume_inflight",
                DEFAULT_CONCURRENCY_LIMITS.per_run_resume_inflight,
            ),
            field="per_run_resume_inflight",
            operation="concurrency",
        ),
    )
    limits.validate()
    return limits


class RuntimeGuardrails:
    def __init__(
        self,
        *,
        rate_limit_rules: Optional[Dict[str, RateLimitRule]] = None,
        concurrency_limits: Optional[ConcurrencyLimits] = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._rate_limit_rules = rate_limit_rules or dict(DEFAULT_RATE_LIMIT_RULES)
        self._concurrency_limits = concurrency_limits or DEFAULT_CONCURRENCY_LIMITS
        self._clock = clock
        self._lock = Lock()
        self._requests: Dict[Tuple[str, str], Deque[float]] = defaultdict(deque)
        self._global_inflight = 0
        self._operation_inflight: Dict[str, int] = defaultdict(int)
        self._run_resume_inflight: Dict[str, int] = defaultdict(int)

    def check_rate_limit(self, *, operation: str, actor_id: str) -> RateLimitDecision:
        rule = self._rate_limit_rules[operation]
        now = self._clock()
        key = (operation, actor_id)

        with self._lock:
            bucket = self._requests[key]
            window_start = now - rule.window_seconds
            while bucket and bucket[0] <= window_start:
                bucket.popleft()

            if len(bucket) >= rule.max_requests:
                retry_after = max(0.001, (bucket[0] + rule.window_seconds) - now)
                return RateLimitDecision(
                    allowed=False,
                    operation=operation,
                    actor_id=actor_id,
                    limit=rule.max_requests,
                    window_seconds=rule.window_seconds,
                    remaining=0,
                    retry_after_seconds=retry_after,
                )

            bucket.append(now)
            remaining = max(0, rule.max_requests - len(bucket))
            return RateLimitDecision(
                allowed=True,
                operation=operation,
                actor_id=actor_id,
                limit=rule.max_requests,
                window_seconds=rule.window_seconds,
                remaining=remaining,
                retry_after_seconds=0.0,
            )

    def acquire_concurrency(self, *, operation: str, run_id: Optional[str] = None) -> tuple[ConcurrencyDecision, Optional[ConcurrencyToken]]:
        with self._lock:
            if self._global_inflight >= self._concurrency_limits.global_inflight:
                return (
                    ConcurrencyDecision(
                        allowed=False,
                        operation=operation,
                        run_id=run_id,
                        limit_type="global_inflight",
                        limit=self._concurrency_limits.global_inflight,
                        current_inflight=self._global_inflight,
                    ),
                    None,
                )

            op_limit = (
                self._concurrency_limits.execute_inflight
                if operation == RUNTIME_OPERATION_MACRO_EXECUTE
                else self._concurrency_limits.resume_inflight
            )
            op_current = self._operation_inflight[operation]
            if op_current >= op_limit:
                return (
                    ConcurrencyDecision(
                        allowed=False,
                        operation=operation,
                        run_id=run_id,
                        limit_type=f"{operation}_inflight",
                        limit=op_limit,
                        current_inflight=op_current,
                    ),
                    None,
                )

            if operation == RUNTIME_OPERATION_RUN_RESUME and run_id:
                run_current = self._run_resume_inflight[run_id]
                if run_current >= self._concurrency_limits.per_run_resume_inflight:
                    return (
                        ConcurrencyDecision(
                            allowed=False,
                            operation=operation,
                            run_id=run_id,
                            limit_type="per_run_resume_inflight",
                            limit=self._concurrency_limits.per_run_resume_inflight,
                            current_inflight=run_current,
                        ),
                        None,
                    )

            self._global_inflight += 1
            self._operation_inflight[operation] += 1
            if operation == RUNTIME_OPERATION_RUN_RESUME and run_id:
                self._run_resume_inflight[run_id] += 1

            return (
                ConcurrencyDecision(
                    allowed=True,
                    operation=operation,
                    run_id=run_id,
                    limit_type=None,
                    limit=0,
                    current_inflight=0,
                ),
                ConcurrencyToken(operation=operation, run_id=run_id),
            )

    def release_concurrency(self, token: ConcurrencyToken) -> None:
        with self._lock:
            self._global_inflight = max(0, self._global_inflight - 1)
            self._operation_inflight[token.operation] = max(0, self._operation_inflight[token.operation] - 1)
            if token.operation == RUNTIME_OPERATION_RUN_RESUME and token.run_id:
                self._run_resume_inflight[token.run_id] = max(0, self._run_resume_inflight[token.run_id] - 1)

    @staticmethod
    def retry_after_header_value(retry_after_seconds: float) -> str:
        return str(max(1, int(math.ceil(retry_after_seconds))))
