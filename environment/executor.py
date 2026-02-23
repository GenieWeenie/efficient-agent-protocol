# environment/executor.py
import asyncio
import logging
import re
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Set
from protocol.models import (
    BatchedMacroRequest,
    ExecutionLimits,
    ExecutionTraceEvent,
    ExecutionTraceEventType,
    StepApprovalDecisionType,
    ToolErrorPayload,
)
from protocol.state_manager import StateManager
from environment.tool_registry import InputValidationError, ToolRegistry

logger = logging.getLogger("eap.environment.executor")


class _AsyncTokenBucket:
    """Async token bucket used to enforce request-rate limits."""

    def __init__(self, requests_per_second: float, capacity: int):
        self._requests_per_second = requests_per_second
        self._capacity = capacity
        self._tokens = float(capacity)
        self._last_refill = time.perf_counter()
        self._lock = asyncio.Lock()

    async def acquire(self) -> float:
        """Acquire one token and return total wait seconds spent."""
        waited_total = 0.0
        while True:
            wait_seconds = 0.0
            async with self._lock:
                now = time.perf_counter()
                elapsed = now - self._last_refill
                if elapsed > 0:
                    self._tokens = min(self._capacity, self._tokens + elapsed * self._requests_per_second)
                    self._last_refill = now

                if self._tokens >= 1.0:
                    self._tokens -= 1.0
                    return waited_total

                wait_seconds = (1.0 - self._tokens) / self._requests_per_second

            await asyncio.sleep(wait_seconds)
            waited_total += wait_seconds


class AsyncLocalExecutor:
    def __init__(
        self,
        state_manager: StateManager,
        registry: ToolRegistry,
        default_execution_limits: Optional[ExecutionLimits] = None,
    ):
        self.state_manager = state_manager
        self.registry = registry
        self.default_execution_limits = default_execution_limits or ExecutionLimits()

    async def execute_macro(self, macro: BatchedMacroRequest) -> dict:
        run_id = f"run_{uuid.uuid4().hex[:12]}"
        run_started_at = datetime.now(timezone.utc)
        run_started_perf = time.perf_counter()
        logger.info(
            "received macro batch",
            extra={"step_count": len(macro.steps), "run_id": run_id},
        )
        retry_policy = macro.retry_policy
        execution_limits = macro.execution_limits or self.default_execution_limits
        step_futures: Dict[str, asyncio.Future] = {
            step.step_id: asyncio.Future() for step in macro.steps
        }
        step_status: Dict[str, Dict[str, str]] = {}
        step_contexts: Dict[str, Dict[str, Any]] = {}
        branch_decisions: Dict[str, Set[str]] = {}
        early_exit_event = asyncio.Event()

        resolved_tool_names: Dict[str, str] = {}
        for step in macro.steps:
            try:
                resolved_tool_names[step.step_id] = self.registry.get_schema(step.tool_name).get(
                    "name", step.tool_name
                )
            except Exception:
                resolved_tool_names[step.step_id] = step.tool_name

        global_semaphore = asyncio.Semaphore(execution_limits.max_global_concurrency)
        per_tool_semaphores: Dict[str, asyncio.Semaphore] = {}
        for tool_name, tool_limits in execution_limits.per_tool.items():
            if tool_limits.max_concurrency is not None:
                per_tool_semaphores[tool_name] = asyncio.Semaphore(tool_limits.max_concurrency)

        global_rate_bucket: Optional[_AsyncTokenBucket] = None
        if execution_limits.global_requests_per_second is not None:
            global_capacity = execution_limits.global_burst_capacity or max(
                1, int(execution_limits.global_requests_per_second)
            )
            global_rate_bucket = _AsyncTokenBucket(execution_limits.global_requests_per_second, global_capacity)

        per_tool_buckets: Dict[str, _AsyncTokenBucket] = {}
        for tool_name, tool_limits in execution_limits.per_tool.items():
            if tool_limits.requests_per_second is None:
                continue
            capacity = tool_limits.burst_capacity or max(1, int(tool_limits.requests_per_second))
            per_tool_buckets[tool_name] = _AsyncTokenBucket(tool_limits.requests_per_second, capacity)

        saturation_metrics: Dict[str, Any] = {
            "global_concurrency_wait_count": 0,
            "global_concurrency_wait_seconds": 0.0,
            "per_tool_concurrency_wait_count": 0,
            "per_tool_concurrency_wait_seconds": 0.0,
            "global_rate_wait_count": 0,
            "global_rate_wait_seconds": 0.0,
            "per_tool_rate_wait_count": 0,
            "per_tool_rate_wait_seconds": 0.0,
            "max_inflight_global": 0,
            "max_inflight_per_tool": {},
            "total_rate_limited_attempts": 0,
            "configured_limits": {
                "max_global_concurrency": execution_limits.max_global_concurrency,
                "global_requests_per_second": execution_limits.global_requests_per_second,
                "global_burst_capacity": execution_limits.global_burst_capacity,
                "per_tool": {
                    name: limit.model_dump(mode="json")
                    for name, limit in execution_limits.per_tool.items()
                },
            },
        }
        inflight_global = 0
        inflight_per_tool: Dict[str, int] = {}
        metric_lock = asyncio.Lock()

        # Map target step_id -> controller step_ids that can activate that target.
        branch_controllers: Dict[str, Set[str]] = {}
        for step in macro.steps:
            if not step.branching:
                continue
            branch_targets = (
                step.branching.true_target_step_ids
                + step.branching.false_target_step_ids
                + step.branching.fallback_target_step_ids
            )
            for target_step_id in branch_targets:
                branch_controllers.setdefault(target_step_id, set()).add(step.step_id)

        reference_pattern = re.compile(r"\$step:([A-Za-z0-9_\-]+)(?:\.([A-Za-z0-9_\.]+))?")

        def evaluate_branch_condition(condition_expression: str) -> bool:
            def replace_reference(match: re.Match) -> str:
                step_id = match.group(1)
                path = match.group(2)
                value: Any = step_contexts.get(step_id)
                if path:
                    for part in path.split("."):
                        if isinstance(value, dict):
                            value = value.get(part)
                        else:
                            value = None
                            break
                return repr(value)

            replaced = reference_pattern.sub(replace_reference, condition_expression)
            replaced = re.sub(r"\btrue\b", "True", replaced, flags=re.IGNORECASE)
            replaced = re.sub(r"\bfalse\b", "False", replaced, flags=re.IGNORECASE)
            try:
                return bool(eval(replaced, {"__builtins__": {}}, {}))
            except Exception as exc:
                logger.warning(
                    "branch condition evaluation failed: %s",
                    str(exc),
                    extra={"condition": condition_expression, "run_id": run_id},
                )
                return False

        def resolve_branch_targets(step, status: str) -> None:
            if not step.branching:
                return

            selected_targets: Set[str] = set()
            if status == "ok":
                condition_is_true = evaluate_branch_condition(step.branching.condition)
                selected_targets = set(
                    step.branching.true_target_step_ids
                    if condition_is_true
                    else step.branching.false_target_step_ids
                )
            elif status == "error":
                selected_targets = set(step.branching.fallback_target_step_ids)
            else:
                selected_targets = set()

            branch_decisions[step.step_id] = selected_targets
            if step.branching.allow_early_exit and not selected_targets:
                early_exit_event.set()
            logger.info(
                "branch resolved",
                extra={
                    "step_id": step.step_id,
                    "run_id": run_id,
                    "selected_targets": sorted(selected_targets),
                    "allow_early_exit": step.branching.allow_early_exit,
                },
            )

        def _tool_limit_key(step_id: str, tool_name_or_hash: str) -> Optional[str]:
            resolved_name = resolved_tool_names.get(step_id, tool_name_or_hash)
            if resolved_name in execution_limits.per_tool:
                return resolved_name
            if tool_name_or_hash in execution_limits.per_tool:
                return tool_name_or_hash
            return None

        async def _record_wait(metric_count_key: str, metric_time_key: str, waited_seconds: float) -> None:
            if waited_seconds <= 0:
                return
            async with metric_lock:
                saturation_metrics[metric_count_key] += 1
                saturation_metrics[metric_time_key] += waited_seconds

        async def _on_slot_acquired(tool_key: Optional[str]) -> None:
            nonlocal inflight_global
            async with metric_lock:
                inflight_global += 1
                if inflight_global > saturation_metrics["max_inflight_global"]:
                    saturation_metrics["max_inflight_global"] = inflight_global
                if tool_key is None:
                    return
                inflight_per_tool[tool_key] = inflight_per_tool.get(tool_key, 0) + 1
                max_map = saturation_metrics["max_inflight_per_tool"]
                prior_max = max_map.get(tool_key, 0)
                if inflight_per_tool[tool_key] > prior_max:
                    max_map[tool_key] = inflight_per_tool[tool_key]

        async def _on_slot_released(tool_key: Optional[str]) -> None:
            nonlocal inflight_global
            async with metric_lock:
                inflight_global = max(0, inflight_global - 1)
                if tool_key is None:
                    return
                current = inflight_per_tool.get(tool_key, 0)
                if current <= 1:
                    inflight_per_tool.pop(tool_key, None)
                else:
                    inflight_per_tool[tool_key] = current - 1

        async def run_step(step):
            logger.info(
                "task queued",
                extra={"step_id": step.step_id, "tool_name": step.tool_name, "run_id": run_id},
            )
            self.state_manager.append_trace_event(
                ExecutionTraceEvent(
                    run_id=run_id,
                    step_id=step.step_id,
                    tool_name=step.tool_name,
                    event_type=ExecutionTraceEventType.QUEUED,
                )
            )
            attempt_count = 0
            step_started_perf = time.perf_counter()
            try:
                controllers = branch_controllers.get(step.step_id, set())
                if controllers:
                    await asyncio.gather(*(step_futures[controller] for controller in controllers))
                    is_activated = any(
                        step.step_id in branch_decisions.get(controller, set())
                        for controller in controllers
                    )
                    if not is_activated:
                        skip_payload = {
                            "status": "skipped",
                            "reason": "branch_not_selected",
                            "step_id": step.step_id,
                            "controllers": sorted(controllers),
                        }
                        step_pointer = self.state_manager.store_and_point(
                            raw_data=skip_payload,
                            summary=f"Step {step.step_id} skipped (branch not selected).",
                            metadata={"status": "skipped", "reason": "branch_not_selected"},
                        )
                        step_status[step.step_id] = {"status": "skipped", "pointer_id": step_pointer["pointer_id"]}
                        step_contexts[step.step_id] = {
                            "pointer_id": step_pointer["pointer_id"],
                            "metadata": step_pointer.get("metadata"),
                            "raw_data": skip_payload,
                            "status": "skipped",
                        }
                        if step.branching:
                            branch_decisions[step.step_id] = set()
                        if not step_futures[step.step_id].done():
                            step_futures[step.step_id].set_result(step_pointer["pointer_id"])
                        logger.info(
                            "task skipped by branch routing",
                            extra={"step_id": step.step_id, "tool_name": step.tool_name, "run_id": run_id},
                        )
                        return step_pointer

                if early_exit_event.is_set():
                    skip_payload = {
                        "status": "skipped",
                        "reason": "early_exit",
                        "step_id": step.step_id,
                    }
                    step_pointer = self.state_manager.store_and_point(
                        raw_data=skip_payload,
                        summary=f"Step {step.step_id} skipped (early exit).",
                        metadata={"status": "skipped", "reason": "early_exit"},
                    )
                    step_status[step.step_id] = {"status": "skipped", "pointer_id": step_pointer["pointer_id"]}
                    step_contexts[step.step_id] = {
                        "pointer_id": step_pointer["pointer_id"],
                        "metadata": step_pointer.get("metadata"),
                        "raw_data": skip_payload,
                        "status": "skipped",
                    }
                    if step.branching:
                        branch_decisions[step.step_id] = set()
                    if not step_futures[step.step_id].done():
                        step_futures[step.step_id].set_result(step_pointer["pointer_id"])
                    logger.info(
                        "task skipped due to early exit",
                        extra={"step_id": step.step_id, "tool_name": step.tool_name, "run_id": run_id},
                    )
                    return step_pointer

                requires_approval = bool(step.approval and step.approval.required)
                approval_decision = macro.approvals.get(step.step_id)
                if requires_approval:
                    self.state_manager.append_trace_event(
                        ExecutionTraceEvent(
                            run_id=run_id,
                            step_id=step.step_id,
                            tool_name=step.tool_name,
                            event_type=ExecutionTraceEventType.APPROVAL_REQUIRED,
                        )
                    )
                    if approval_decision is None:
                        pending_payload = {
                            "status": "paused",
                            "reason": "awaiting_approval",
                            "step_id": step.step_id,
                            "approval_prompt": step.approval.prompt if step.approval else None,
                        }
                        step_pointer = self.state_manager.store_and_point(
                            raw_data=pending_payload,
                            summary=f"Step {step.step_id} paused awaiting approval.",
                            metadata={
                                "status": "paused",
                                "reason": "awaiting_approval",
                                "approval_prompt": step.approval.prompt if step.approval else None,
                            },
                        )
                        step_status[step.step_id] = {
                            "status": "paused",
                            "pointer_id": step_pointer["pointer_id"],
                        }
                        step_contexts[step.step_id] = {
                            "pointer_id": step_pointer["pointer_id"],
                            "metadata": step_pointer.get("metadata"),
                            "raw_data": pending_payload,
                            "status": "paused",
                        }
                        if step.branching:
                            branch_decisions[step.step_id] = set()
                        if not step_futures[step.step_id].done():
                            step_futures[step.step_id].set_result(step_pointer["pointer_id"])
                        logger.info(
                            "task paused awaiting approval",
                            extra={"step_id": step.step_id, "tool_name": step.tool_name, "run_id": run_id},
                        )
                        return step_pointer

                    if approval_decision.decision == StepApprovalDecisionType.REJECT:
                        rejection_reason = approval_decision.reason or "Rejected by reviewer."
                        error_payload = ToolErrorPayload(
                            error_type="approval_rejected",
                            message=rejection_reason,
                            step_id=step.step_id,
                            tool_name=step.tool_name,
                            details={"approval_prompt": step.approval.prompt if step.approval else None},
                        )
                        self.state_manager.append_trace_event(
                            ExecutionTraceEvent(
                                run_id=run_id,
                                step_id=step.step_id,
                                tool_name=step.tool_name,
                                event_type=ExecutionTraceEventType.REJECTED,
                                attempt=1,
                                error=error_payload,
                            )
                        )
                        rejection_payload = error_payload.model_dump(mode="json")
                        step_pointer = self.state_manager.store_and_point(
                            raw_data=rejection_payload,
                            summary=f"Step {step.step_id} rejected at approval checkpoint.",
                            metadata={"status": "rejected", "error_type": "approval_rejected"},
                        )
                        step_status[step.step_id] = {
                            "status": "rejected",
                            "pointer_id": step_pointer["pointer_id"],
                        }
                        step_contexts[step.step_id] = {
                            "pointer_id": step_pointer["pointer_id"],
                            "metadata": step_pointer.get("metadata"),
                            "raw_data": rejection_payload,
                            "status": "rejected",
                        }
                        resolve_branch_targets(step, status="error")
                        if not step_futures[step.step_id].done():
                            step_futures[step.step_id].set_result(step_pointer["pointer_id"])
                        logger.info(
                            "task rejected at approval checkpoint",
                            extra={"step_id": step.step_id, "tool_name": step.tool_name, "run_id": run_id},
                        )
                        return step_pointer

                    self.state_manager.append_trace_event(
                        ExecutionTraceEvent(
                            run_id=run_id,
                            step_id=step.step_id,
                            tool_name=step.tool_name,
                            event_type=ExecutionTraceEventType.APPROVED,
                        )
                    )

                resolved_args = {}
                input_pointer_ids = {}
                for key, val in step.arguments.items():
                    # Forgiving Routing: Handles "$step:id" and "$id"
                    if isinstance(val, str) and val.startswith("$"):
                        ref_step_id = val.replace("$step:", "").replace("$", "")
                        if ref_step_id not in step_futures:
                            raise KeyError(f"Step reference '{ref_step_id}' failed.")

                        pointer_id = await step_futures[ref_step_id]
                        dependency_status = step_status.get(ref_step_id, {}).get("status")
                        if dependency_status != "ok":
                            raise KeyError(
                                f"Dependency step '{ref_step_id}' did not complete successfully ({dependency_status})."
                            )
                        input_pointer_ids[key] = pointer_id
                        resolved_args[key] = self.state_manager.retrieve(pointer_id)
                    elif isinstance(val, str) and val.startswith("ptr_"):
                        input_pointer_ids[key] = val
                        resolved_args[key] = self.state_manager.retrieve(val)
                    else:
                        resolved_args[key] = val

                self.registry.validate_arguments(step.tool_name, resolved_args)
                tool_func = self.registry.get_tool(step.tool_name)
                delay = retry_policy.initial_delay_seconds
                tool_limit_key = _tool_limit_key(step.step_id, step.tool_name)
                tool_semaphore = per_tool_semaphores.get(tool_limit_key) if tool_limit_key else None
                tool_bucket = per_tool_buckets.get(tool_limit_key) if tool_limit_key else None
                while True:
                    attempt_count += 1
                    acquired_global_slot = False
                    acquired_tool_slot = False
                    try:
                        global_wait_started = time.perf_counter()
                        await global_semaphore.acquire()
                        acquired_global_slot = True
                        await _record_wait(
                            "global_concurrency_wait_count",
                            "global_concurrency_wait_seconds",
                            time.perf_counter() - global_wait_started,
                        )

                        if tool_semaphore is not None:
                            tool_wait_started = time.perf_counter()
                            await tool_semaphore.acquire()
                            acquired_tool_slot = True
                            await _record_wait(
                                "per_tool_concurrency_wait_count",
                                "per_tool_concurrency_wait_seconds",
                                time.perf_counter() - tool_wait_started,
                            )

                        await _on_slot_acquired(tool_limit_key)

                        was_rate_limited = False
                        if global_rate_bucket is not None:
                            global_rate_wait = await global_rate_bucket.acquire()
                            await _record_wait(
                                "global_rate_wait_count",
                                "global_rate_wait_seconds",
                                global_rate_wait,
                            )
                            if global_rate_wait > 0:
                                was_rate_limited = True

                        if tool_bucket is not None:
                            tool_rate_wait = await tool_bucket.acquire()
                            await _record_wait(
                                "per_tool_rate_wait_count",
                                "per_tool_rate_wait_seconds",
                                tool_rate_wait,
                            )
                            if tool_rate_wait > 0:
                                was_rate_limited = True

                        if was_rate_limited:
                            async with metric_lock:
                                saturation_metrics["total_rate_limited_attempts"] += 1

                        self.state_manager.append_trace_event(
                            ExecutionTraceEvent(
                                run_id=run_id,
                                step_id=step.step_id,
                                tool_name=step.tool_name,
                                event_type=ExecutionTraceEventType.STARTED,
                                attempt=attempt_count,
                                resolved_arguments=resolved_args,
                                input_pointer_ids=input_pointer_ids or None,
                            )
                        )
                        raw_output = await asyncio.to_thread(tool_func, **resolved_args)
                        break
                    except Exception as exc:
                        error_name = exc.__class__.__name__
                        error_payload = ToolErrorPayload(
                            error_type="tool_execution_error",
                            message=str(exc),
                            step_id=step.step_id,
                            tool_name=step.tool_name,
                            details={"attempts": attempt_count},
                        )
                        retryable = error_name in retry_policy.retryable_error_types
                        if (not retryable) or (attempt_count >= retry_policy.max_attempts):
                            raise
                        self.state_manager.append_trace_event(
                            ExecutionTraceEvent(
                                run_id=run_id,
                                step_id=step.step_id,
                                tool_name=step.tool_name,
                                event_type=ExecutionTraceEventType.RETRIED,
                                attempt=attempt_count,
                                retry_delay_seconds=delay,
                                error=error_payload,
                                resolved_arguments=resolved_args,
                                input_pointer_ids=input_pointer_ids or None,
                            )
                        )
                        logger.warning(
                            "task retrying",
                            extra={
                                "step_id": step.step_id,
                                "tool_name": step.tool_name,
                                "attempt": attempt_count,
                                "error_type": error_name,
                                "run_id": run_id,
                            },
                        )
                        await asyncio.sleep(delay)
                        delay *= retry_policy.backoff_multiplier
                    finally:
                        if acquired_global_slot or acquired_tool_slot:
                            await _on_slot_released(tool_limit_key)
                        if acquired_tool_slot and tool_semaphore is not None:
                            tool_semaphore.release()
                        if acquired_global_slot:
                            global_semaphore.release()

                step_pointer = self.state_manager.store_and_point(
                    raw_data=raw_output,
                    summary=f"Completed step {step.step_id} successfully.",
                )
                step_duration_ms = round((time.perf_counter() - step_started_perf) * 1000, 3)
                self.state_manager.append_trace_event(
                    ExecutionTraceEvent(
                        run_id=run_id,
                        step_id=step.step_id,
                        tool_name=step.tool_name,
                        event_type=ExecutionTraceEventType.COMPLETED,
                        attempt=attempt_count,
                        resolved_arguments=resolved_args,
                        input_pointer_ids=input_pointer_ids or None,
                        output_pointer_id=step_pointer["pointer_id"],
                        duration_ms=step_duration_ms,
                    )
                )
                step_status[step.step_id] = {"status": "ok", "pointer_id": step_pointer["pointer_id"]}
                step_contexts[step.step_id] = {
                    "pointer_id": step_pointer["pointer_id"],
                    "metadata": step_pointer.get("metadata"),
                    "raw_data": raw_output,
                    "status": "ok",
                }
                resolve_branch_targets(step, status="ok")
                if not step_futures[step.step_id].done():
                    step_futures[step.step_id].set_result(step_pointer["pointer_id"])
                logger.info(
                    "task finished",
                    extra={"step_id": step.step_id, "tool_name": step.tool_name, "run_id": run_id},
                )
                return step_pointer
            except Exception as exc:
                if isinstance(exc, InputValidationError):
                    error_type = "validation_error"
                elif isinstance(exc, KeyError):
                    error_type = "dependency_error"
                else:
                    error_type = "tool_execution_error"

                logger.error(
                    "task failed: %s",
                    str(exc),
                    extra={"step_id": step.step_id, "tool_name": step.tool_name, "run_id": run_id},
                )
                error_payload = ToolErrorPayload(
                    error_type=error_type,
                    message=str(exc),
                    step_id=step.step_id,
                    tool_name=step.tool_name,
                    details={"attempts": attempt_count},
                ).model_dump()
                step_duration_ms = round((time.perf_counter() - step_started_perf) * 1000, 3)
                self.state_manager.append_trace_event(
                    ExecutionTraceEvent(
                        run_id=run_id,
                        step_id=step.step_id,
                        tool_name=step.tool_name,
                        event_type=ExecutionTraceEventType.FAILED,
                        attempt=max(1, attempt_count),
                        error=ToolErrorPayload(**error_payload),
                        duration_ms=step_duration_ms,
                    )
                )
                step_pointer = self.state_manager.store_and_point(
                    raw_data=error_payload,
                    summary=f"Step {step.step_id} failed with {error_type}.",
                    metadata={"status": "error", "error_type": error_type},
                )
                step_status[step.step_id] = {"status": "error", "pointer_id": step_pointer["pointer_id"]}
                step_contexts[step.step_id] = {
                    "pointer_id": step_pointer["pointer_id"],
                    "metadata": step_pointer.get("metadata"),
                    "raw_data": error_payload,
                    "status": "error",
                }
                resolve_branch_targets(step, status="error")
                if not step_futures[step.step_id].done():
                    step_futures[step.step_id].set_result(step_pointer["pointer_id"])
                return step_pointer

        tasks = [asyncio.create_task(run_step(step)) for step in macro.steps]
        results = await asyncio.gather(*tasks)
        final_result = results[-1] if results else None

        run_completed_at = datetime.now(timezone.utc)
        succeeded_steps = sum(1 for item in step_status.values() if item.get("status") == "ok")
        failed_steps = sum(
            1 for item in step_status.values() if item.get("status") in {"error", "rejected", "paused"}
        )
        approval_required_steps = sum(
            1 for step in macro.steps if step.approval is not None and step.approval.required
        )
        approval_paused_steps = sum(1 for item in step_status.values() if item.get("status") == "paused")
        approval_rejected_steps = sum(1 for item in step_status.values() if item.get("status") == "rejected")
        approval_approved_steps = max(
            0,
            approval_required_steps - approval_paused_steps - approval_rejected_steps,
        )
        self.state_manager.store_execution_summary(
            run_id=run_id,
            started_at_utc=run_started_at.isoformat(),
            completed_at_utc=run_completed_at.isoformat(),
            total_steps=len(macro.steps),
            succeeded_steps=succeeded_steps,
            failed_steps=failed_steps,
            total_duration_ms=round((time.perf_counter() - run_started_perf) * 1000, 3),
            final_pointer_id=final_result["pointer_id"] if final_result else None,
        )

        if final_result:
            final_result.setdefault("metadata", {})
            final_result["metadata"]["execution_run_id"] = run_id
            final_result["metadata"]["approval_metrics"] = {
                "required_steps": approval_required_steps,
                "approved_steps": approval_approved_steps,
                "rejected_steps": approval_rejected_steps,
                "paused_steps": approval_paused_steps,
            }
            final_result["metadata"]["saturation_metrics"] = {
                **saturation_metrics,
                "global_concurrency_wait_seconds": round(
                    saturation_metrics["global_concurrency_wait_seconds"], 6
                ),
                "per_tool_concurrency_wait_seconds": round(
                    saturation_metrics["per_tool_concurrency_wait_seconds"], 6
                ),
                "global_rate_wait_seconds": round(
                    saturation_metrics["global_rate_wait_seconds"], 6
                ),
                "per_tool_rate_wait_seconds": round(
                    saturation_metrics["per_tool_rate_wait_seconds"], 6
                ),
            }
        return final_result
