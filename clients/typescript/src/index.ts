/**
 * EAP TypeScript Client
 *
 * Lightweight client for the EAP Runtime HTTP API.
 * Supports macro execution, run management, and pointer retrieval.
 */

export interface ToolCall {
  step_id: string;
  tool_name: string;
  arguments: Record<string, unknown>;
  depends_on?: string[];
}

export interface RetryPolicy {
  max_attempts?: number;
  initial_delay_seconds?: number;
  backoff_multiplier?: number;
  retryable_error_types?: string[];
}

export interface MacroRequest {
  steps: ToolCall[];
  retry_policy?: RetryPolicy;
}

export interface ExecutionResult {
  pointer_id: string;
  summary: string;
  metadata: Record<string, unknown>;
}

export interface RunSummary {
  run_id: string;
  started_at_utc: string;
  completed_at_utc: string;
  total_steps: number;
  succeeded_steps: number;
  failed_steps: number;
  total_duration_ms: number;
  final_pointer_id: string | null;
}

export interface EAPClientOptions {
  baseUrl: string;
  token?: string;
  timeoutMs?: number;
}

export class EAPClient {
  private baseUrl: string;
  private token?: string;
  private timeoutMs: number;

  constructor(options: EAPClientOptions) {
    this.baseUrl = options.baseUrl.replace(/\/+$/, "");
    this.token = options.token;
    this.timeoutMs = options.timeoutMs ?? 60_000;
  }

  private headers(): Record<string, string> {
    const h: Record<string, string> = { "Content-Type": "application/json" };
    if (this.token) {
      h["Authorization"] = `Bearer ${this.token}`;
    }
    return h;
  }

  async executeMacro(
    macro: MacroRequest,
    actorId?: string,
  ): Promise<ExecutionResult> {
    const body: Record<string, unknown> = { macro };
    if (actorId) {
      body.actor_metadata = { actor_id: actorId };
    }
    const resp = await fetch(`${this.baseUrl}/v1/eap/macro/execute`, {
      method: "POST",
      headers: this.headers(),
      body: JSON.stringify(body),
      signal: AbortSignal.timeout(this.timeoutMs),
    });
    if (!resp.ok) {
      const text = await resp.text();
      throw new Error(`EAP execute failed (${resp.status}): ${text}`);
    }
    return resp.json() as Promise<ExecutionResult>;
  }

  async resumeRun(runId: string, approvals?: Record<string, string>): Promise<ExecutionResult> {
    const body: Record<string, unknown> = {};
    if (approvals) {
      body.approvals = approvals;
    }
    const resp = await fetch(`${this.baseUrl}/v1/eap/runs/${runId}/resume`, {
      method: "POST",
      headers: this.headers(),
      body: JSON.stringify(body),
      signal: AbortSignal.timeout(this.timeoutMs),
    });
    if (!resp.ok) {
      const text = await resp.text();
      throw new Error(`EAP resume failed (${resp.status}): ${text}`);
    }
    return resp.json() as Promise<ExecutionResult>;
  }

  async getRun(runId: string): Promise<RunSummary> {
    const resp = await fetch(`${this.baseUrl}/v1/eap/runs/${runId}`, {
      method: "GET",
      headers: this.headers(),
      signal: AbortSignal.timeout(this.timeoutMs),
    });
    if (!resp.ok) {
      const text = await resp.text();
      throw new Error(`EAP get run failed (${resp.status}): ${text}`);
    }
    return resp.json() as Promise<RunSummary>;
  }

  async getPointerSummary(pointerId: string): Promise<Record<string, unknown>> {
    const resp = await fetch(
      `${this.baseUrl}/v1/eap/pointers/${pointerId}/summary`,
      {
        method: "GET",
        headers: this.headers(),
        signal: AbortSignal.timeout(this.timeoutMs),
      },
    );
    if (!resp.ok) {
      const text = await resp.text();
      throw new Error(`EAP pointer summary failed (${resp.status}): ${text}`);
    }
    return resp.json() as Promise<Record<string, unknown>>;
  }
}
