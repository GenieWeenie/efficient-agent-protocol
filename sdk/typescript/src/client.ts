import {
  ApiErrorPayload,
  BatchedMacroRequest,
  ChatRequest,
  ChatResponse,
  ExecuteMacroRequest,
  ExecuteMacroResponse,
  GenerateMacroRequest,
  GenerateMacroResponse,
} from "./types.js";

export interface EAPClientOptions {
  baseUrl: string;
  apiKey?: string;
  model?: string;
  timeoutMs?: number;
  fetchImpl?: typeof fetch;
}

export class EAPApiError extends Error {
  readonly payload?: ApiErrorPayload;
  readonly statusCode: number;

  constructor(message: string, statusCode: number, payload?: ApiErrorPayload) {
    super(message);
    this.name = "EAPApiError";
    this.statusCode = statusCode;
    this.payload = payload;
  }
}

export class EAPClient {
  private readonly baseUrl: string;
  private readonly apiKey?: string;
  private readonly model?: string;
  private readonly timeoutMs: number;
  private readonly fetchImpl: typeof fetch;

  constructor(options: EAPClientOptions) {
    this.baseUrl = options.baseUrl.replace(/\/+$/, "");
    this.apiKey = options.apiKey;
    this.model = options.model;
    this.timeoutMs = options.timeoutMs ?? 30_000;
    this.fetchImpl = options.fetchImpl ?? fetch;
  }

  async chat(request: ChatRequest): Promise<ChatResponse> {
    const payload: ChatRequest = {
      ...request,
      model: request.model ?? this.model,
    };
    return this.request<ChatResponse>("/v1/eap/chat", payload);
  }

  async generateMacro(request: GenerateMacroRequest): Promise<GenerateMacroResponse> {
    return this.request<GenerateMacroResponse>("/v1/eap/macro/generate", request);
  }

  async executeMacro(request: ExecuteMacroRequest): Promise<ExecuteMacroResponse> {
    return this.request<ExecuteMacroResponse>("/v1/eap/macro/execute", request);
  }

  async executeMacroFromDefinition(macro: BatchedMacroRequest): Promise<ExecuteMacroResponse> {
    return this.executeMacro({ macro });
  }

  private async request<TResponse>(path: string, payload: object): Promise<TResponse> {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), this.timeoutMs);
    try {
      const headers: Record<string, string> = {
        "Content-Type": "application/json",
        Accept: "application/json",
      };
      if (this.apiKey) {
        headers.Authorization = `Bearer ${this.apiKey}`;
      }

      const response = await this.fetchImpl(`${this.baseUrl}${path}`, {
        method: "POST",
        headers,
        body: JSON.stringify(payload),
        signal: controller.signal,
      });
      const textBody = await response.text();
      const parsedBody = textBody ? JSON.parse(textBody) : {};

      if (!response.ok) {
        const errorPayload = parsedBody as ApiErrorPayload;
        throw new EAPApiError(
          errorPayload.message ?? `Request failed with status ${response.status}`,
          response.status,
          errorPayload,
        );
      }
      return parsedBody as TResponse;
    } catch (error) {
      if (error instanceof EAPApiError) {
        throw error;
      }
      if (error instanceof Error && error.name === "AbortError") {
        throw new EAPApiError(
          `Request timed out after ${this.timeoutMs}ms`,
          408,
          { error_type: "timeout", message: "Request timed out." },
        );
      }
      const message = error instanceof Error ? error.message : String(error);
      throw new EAPApiError(message, 500, {
        error_type: "transport_error",
        message,
      });
    } finally {
      clearTimeout(timer);
    }
  }
}
