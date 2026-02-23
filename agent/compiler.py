# agent/compiler.py
import json
from typing import Any, Dict, Optional, Union
from protocol.models import (
    BatchedMacroRequest,
    ExecutionLimits,
    PersistedWorkflowGraph,
    RetryPolicy,
)


def _extract_first_json_object(raw_payload: str, error_message: str) -> Dict[str, Any]:
    """Extract the first top-level JSON object embedded in arbitrary text."""
    decoder = json.JSONDecoder()
    start_index = raw_payload.find("{")
    while start_index != -1:
        try:
            parsed, _ = decoder.raw_decode(raw_payload, start_index)
        except json.JSONDecodeError:
            start_index = raw_payload.find("{", start_index + 1)
            continue
        if isinstance(parsed, dict):
            return parsed
        start_index = raw_payload.find("{", start_index + 1)
    raise ValueError(error_message)

class MacroCompiler:
    """
    An advanced compiler that sanitizes and 'auto-heals' common LLM 
    JSON hallucinations before validation.
    """
    @staticmethod
    def compile(raw_llm_output: Union[str, Dict[str, Any]]) -> BatchedMacroRequest:
        try:
            # 1. Extract JSON from potential markdown or conversational noise
            if isinstance(raw_llm_output, str):
                parsed_data = _extract_first_json_object(
                    raw_llm_output,
                    error_message="No JSON object found in output.",
                )
            else:
                parsed_data = raw_llm_output

            # 2. AUTO-HEALING: Fix common hallucinations for smaller models
            if "steps" in parsed_data:
                for step in parsed_data["steps"]:
                    # Fix 'tool' -> 'tool_name'
                    if "tool" in step and "tool_name" not in step:
                        step["tool_name"] = step.pop("tool")
                    
                    # Ensure step_id exists
                    if "step_id" not in step:
                        step["step_id"] = f"auto_step_{hash(str(step)) % 1000}"

            # 3. Final Pydantic validation
            return BatchedMacroRequest(**parsed_data)
            
        except Exception as e:
            raise ValueError(f"Compiler Error: {str(e)}")


class WorkflowGraphCompiler:
    """Compile persisted workflow graph payloads into executable macro requests."""

    @staticmethod
    def _extract_json_object(raw_payload: str) -> Dict[str, Any]:
        return _extract_first_json_object(
            raw_payload,
            error_message="No JSON object found in workflow graph payload.",
        )

    @staticmethod
    def _coerce_graph_payload(
        raw_graph: Union[str, Dict[str, Any], PersistedWorkflowGraph],
    ) -> PersistedWorkflowGraph:
        if isinstance(raw_graph, PersistedWorkflowGraph):
            return raw_graph
        if isinstance(raw_graph, str):
            parsed = WorkflowGraphCompiler._extract_json_object(raw_graph)
            return PersistedWorkflowGraph(**parsed)
        if isinstance(raw_graph, dict):
            return PersistedWorkflowGraph(**raw_graph)
        raise ValueError("Unsupported workflow graph payload type.")

    @staticmethod
    def compile_graph(
        raw_graph: Union[str, Dict[str, Any], PersistedWorkflowGraph],
    ) -> PersistedWorkflowGraph:
        try:
            return WorkflowGraphCompiler._coerce_graph_payload(raw_graph)
        except Exception as exc:
            raise ValueError(f"Workflow graph validation failed: {exc}") from exc

    @staticmethod
    def compile_to_macro(
        raw_graph: Union[str, Dict[str, Any], PersistedWorkflowGraph],
        return_final_state_only: bool = True,
        retry_policy: Optional[Union[RetryPolicy, Dict[str, Any]]] = None,
        execution_limits: Optional[Union[ExecutionLimits, Dict[str, Any]]] = None,
    ) -> BatchedMacroRequest:
        graph = WorkflowGraphCompiler.compile_graph(raw_graph)
        try:
            retry_policy_model: Optional[RetryPolicy] = None
            if retry_policy is not None:
                retry_policy_model = (
                    retry_policy if isinstance(retry_policy, RetryPolicy) else RetryPolicy(**retry_policy)
                )

            execution_limits_model: Optional[ExecutionLimits] = None
            if execution_limits is not None:
                execution_limits_model = (
                    execution_limits
                    if isinstance(execution_limits, ExecutionLimits)
                    else ExecutionLimits(**execution_limits)
                )

            return graph.to_batched_macro_request(
                return_final_state_only=return_final_state_only,
                retry_policy=retry_policy_model,
                execution_limits=execution_limits_model,
            )
        except Exception as exc:
            raise ValueError(f"Workflow graph compile failed: {exc}") from exc
