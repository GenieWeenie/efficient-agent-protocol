# agent/compiler.py
import json
import re
from typing import Any, Dict, Optional, Union
from protocol.models import (
    BatchedMacroRequest,
    ExecutionLimits,
    PersistedWorkflowGraph,
    RetryPolicy,
)

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
                # Use regex to find the first '{' and last '}' to strip conversational text
                match = re.search(r'\{.*\}', raw_llm_output, re.DOTALL)
                if not match:
                    raise ValueError("No JSON object found in output.")
                
                cleaned_output = match.group(0)
                parsed_data = json.loads(cleaned_output)
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
        match = re.search(r"\{.*\}", raw_payload, re.DOTALL)
        if not match:
            raise ValueError("No JSON object found in workflow graph payload.")
        return json.loads(match.group(0))

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
