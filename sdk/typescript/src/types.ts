export type Role = "system" | "user" | "assistant";

export interface ApiEnvelope {
  request_id: string;
  timestamp_utc: string;
}

export interface ApiErrorPayload {
  error_type: string;
  message: string;
  details?: Record<string, unknown>;
}

export interface ChatMessage {
  role: Role;
  content: string;
}

export interface ChatRequest {
  model?: string;
  messages: ChatMessage[];
  temperature?: number;
}

export interface ChatResponse extends ApiEnvelope {
  content: string;
}

export interface BranchingRule {
  condition: string;
  true_target_step_ids?: string[];
  false_target_step_ids?: string[];
  fallback_target_step_ids?: string[];
  allow_early_exit?: boolean;
}

export interface StepApprovalCheckpoint {
  required?: boolean;
  prompt?: string;
}

export type StepApprovalDecisionType = "approve" | "reject";

export interface StepApprovalDecision {
  decision: StepApprovalDecisionType;
  reason?: string;
}

export interface ToolCall {
  step_id: string;
  tool_name: string;
  arguments: Record<string, unknown>;
  branching?: BranchingRule;
  approval?: StepApprovalCheckpoint;
}

export interface RetryPolicy {
  max_attempts?: number;
  initial_delay_seconds?: number;
  backoff_multiplier?: number;
  retryable_error_types?: string[];
}

export interface ToolExecutionLimit {
  max_concurrency?: number;
  requests_per_second?: number;
  burst_capacity?: number;
}

export interface ExecutionLimits {
  max_global_concurrency?: number;
  global_requests_per_second?: number;
  global_burst_capacity?: number;
  per_tool?: Record<string, ToolExecutionLimit>;
}

export interface BatchedMacroRequest {
  steps: ToolCall[];
  return_final_state_only?: boolean;
  retry_policy?: RetryPolicy;
  execution_limits?: ExecutionLimits;
  approvals?: Record<string, StepApprovalDecision>;
}

export interface GenerateMacroRequest {
  query: string;
  agent_manifest: Record<string, unknown>;
  memory_context?: string;
}

export interface GenerateMacroResponse extends ApiEnvelope {
  macro: BatchedMacroRequest;
}

export interface ExecuteMacroRequest {
  macro: BatchedMacroRequest;
}

export interface ExecuteMacroResponse extends ApiEnvelope {
  pointer_id: string;
  summary: string;
  metadata?: Record<string, unknown>;
}
