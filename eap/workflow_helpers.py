"""Higher-level helpers for declarative workflow definitions.

Provides a fluent builder API and convenience functions so users can
define EAP workflows without manually constructing ``BatchedMacroRequest``
payloads.

Example::

    from eap.workflow_helpers import WorkflowBuilder

    wf = (
        WorkflowBuilder()
        .step("fetch", "scrape_url", url="https://example.com")
        .step("analyze", "analyze_data", data="$step:fetch")
        .with_retry(max_attempts=3, retryable_errors=["TimeoutError"])
        .build()
    )
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

from eap.protocol import BatchedMacroRequest, RetryPolicy, ToolCall


class WorkflowBuilder:
    """Fluent builder for constructing ``BatchedMacroRequest`` instances."""

    def __init__(self) -> None:
        self._steps: List[ToolCall] = []
        self._retry_policy: Optional[RetryPolicy] = None

    def step(
        self,
        step_id: str,
        tool_name: str,
        depends_on: Optional[Sequence[str]] = None,
        **arguments: Any,
    ) -> WorkflowBuilder:
        """Add a step to the workflow.

        Keyword arguments are passed as tool arguments.  Use ``$step:<id>``
        syntax in argument values to reference outputs of previous steps.
        """
        self._steps.append(
            ToolCall(
                step_id=step_id,
                tool_name=tool_name,
                arguments=dict(arguments),
                depends_on=list(depends_on) if depends_on else None,
            )
        )
        return self

    def with_retry(
        self,
        max_attempts: int = 3,
        initial_delay: float = 1.0,
        backoff: float = 2.0,
        retryable_errors: Optional[List[str]] = None,
    ) -> WorkflowBuilder:
        """Configure the retry policy for the workflow."""
        self._retry_policy = RetryPolicy(
            max_attempts=max_attempts,
            initial_delay_seconds=initial_delay,
            backoff_multiplier=backoff,
            retryable_error_types=retryable_errors or [],
        )
        return self

    def build(self) -> BatchedMacroRequest:
        """Build and return the ``BatchedMacroRequest``."""
        if not self._steps:
            raise ValueError("Workflow must have at least one step.")
        kwargs: Dict[str, Any] = {"steps": list(self._steps)}
        if self._retry_policy is not None:
            kwargs["retry_policy"] = self._retry_policy
        return BatchedMacroRequest(**kwargs)


def linear_pipeline(
    steps: Sequence[Dict[str, Any]],
    retry_policy: Optional[RetryPolicy] = None,
) -> BatchedMacroRequest:
    """Build a linear pipeline where each step depends on the previous one.

    Each entry in ``steps`` should be a dict with keys ``step_id``,
    ``tool_name``, and ``arguments``.  Dependencies are automatically
    chained so step N receives the output of step N-1.

    Example::

        macro = linear_pipeline([
            {"step_id": "s1", "tool_name": "read_local_file", "arguments": {"path": "data.csv"}},
            {"step_id": "s2", "tool_name": "analyze_data", "arguments": {"data": "$step:s1"}},
        ])
    """
    tool_calls: List[ToolCall] = []
    for i, entry in enumerate(steps):
        depends = [steps[i - 1]["step_id"]] if i > 0 else None
        tool_calls.append(
            ToolCall(
                step_id=entry["step_id"],
                tool_name=entry["tool_name"],
                arguments=entry.get("arguments", {}),
                depends_on=depends,
            )
        )
    kwargs: Dict[str, Any] = {"steps": tool_calls}
    if retry_policy is not None:
        kwargs["retry_policy"] = retry_policy
    return BatchedMacroRequest(**kwargs)
