package eapsdk

type APIEnvelope struct {
	RequestID    string `json:"request_id"`
	TimestampUTC string `json:"timestamp_utc"`
}

type APIErrorPayload struct {
	ErrorType string                 `json:"error_type"`
	Message   string                 `json:"message"`
	Details   map[string]interface{} `json:"details,omitempty"`
}

type ChatMessage struct {
	Role    string `json:"role"`
	Content string `json:"content"`
}

type ChatRequest struct {
	Model       string        `json:"model,omitempty"`
	Messages    []ChatMessage `json:"messages"`
	Temperature *float64      `json:"temperature,omitempty"`
}

type ChatResponse struct {
	APIEnvelope
	Content string `json:"content"`
}

type BranchingRule struct {
	Condition             string   `json:"condition"`
	TrueTargetStepIDs     []string `json:"true_target_step_ids,omitempty"`
	FalseTargetStepIDs    []string `json:"false_target_step_ids,omitempty"`
	FallbackTargetStepIDs []string `json:"fallback_target_step_ids,omitempty"`
	AllowEarlyExit        bool     `json:"allow_early_exit,omitempty"`
}

type StepApprovalCheckpoint struct {
	Required bool   `json:"required,omitempty"`
	Prompt   string `json:"prompt,omitempty"`
}

type StepApprovalDecision struct {
	Decision string `json:"decision"`
	Reason   string `json:"reason,omitempty"`
}

type ToolCall struct {
	StepID    string                 `json:"step_id"`
	ToolName  string                 `json:"tool_name"`
	Arguments map[string]interface{} `json:"arguments"`
	Branching *BranchingRule         `json:"branching,omitempty"`
	Approval  *StepApprovalCheckpoint `json:"approval,omitempty"`
}

type RetryPolicy struct {
	MaxAttempts        int      `json:"max_attempts,omitempty"`
	InitialDelaySecond float64  `json:"initial_delay_seconds,omitempty"`
	BackoffMultiplier  float64  `json:"backoff_multiplier,omitempty"`
	RetryableErrorType []string `json:"retryable_error_types,omitempty"`
}

type ToolExecutionLimit struct {
	MaxConcurrency   *int     `json:"max_concurrency,omitempty"`
	RequestsPerSec   *float64 `json:"requests_per_second,omitempty"`
	BurstCapacity    *int     `json:"burst_capacity,omitempty"`
}

type ExecutionLimits struct {
	MaxGlobalConcurrency   *int                          `json:"max_global_concurrency,omitempty"`
	GlobalRequestsPerSec   *float64                      `json:"global_requests_per_second,omitempty"`
	GlobalBurstCapacity    *int                          `json:"global_burst_capacity,omitempty"`
	PerTool                map[string]ToolExecutionLimit `json:"per_tool,omitempty"`
}

type BatchedMacroRequest struct {
	Steps                []ToolCall       `json:"steps"`
	ReturnFinalStateOnly bool             `json:"return_final_state_only,omitempty"`
	RetryPolicy          *RetryPolicy     `json:"retry_policy,omitempty"`
	ExecutionLimits      *ExecutionLimits `json:"execution_limits,omitempty"`
	Approvals            map[string]StepApprovalDecision `json:"approvals,omitempty"`
}

type GenerateMacroRequest struct {
	Query         string                 `json:"query"`
	AgentManifest map[string]interface{} `json:"agent_manifest"`
	MemoryContext string                 `json:"memory_context,omitempty"`
}

type GenerateMacroResponse struct {
	APIEnvelope
	Macro BatchedMacroRequest `json:"macro"`
}

type ExecuteMacroRequest struct {
	Macro BatchedMacroRequest `json:"macro"`
}

type ExecuteMacroResponse struct {
	APIEnvelope
	PointerID string                 `json:"pointer_id"`
	Summary   string                 `json:"summary"`
	Metadata  map[string]interface{} `json:"metadata,omitempty"`
}
