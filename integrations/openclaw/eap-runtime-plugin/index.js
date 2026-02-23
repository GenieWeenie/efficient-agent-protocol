const DEFAULT_TIMEOUT_MS = 15_000;
const PLUGIN_ID = "eap-runtime";

/**
 * @typedef {{ baseUrl: string, apiKey?: string, timeoutMs?: number }} EAPRuntimeConfig
 */

/**
 * @typedef {{
 *   registerTool: (name: string, spec: Record<string, unknown>, handler: (args: Record<string, unknown>) => Promise<Record<string, unknown>>) => void,
 *   config?: Record<string, unknown>,
 *   plugin?: { config?: Record<string, unknown> },
 * }} OpenClawPluginAPI
 */

function parseTimeout(value) {
  if (typeof value === "number" && Number.isFinite(value) && value > 0) {
    return Math.floor(value);
  }
  if (typeof value === "string" && value.trim().length > 0) {
    const parsed = Number.parseInt(value, 10);
    if (Number.isFinite(parsed) && parsed > 0) {
      return parsed;
    }
  }
  return DEFAULT_TIMEOUT_MS;
}

export function normalizeBaseUrl(baseUrl) {
  return String(baseUrl || "").trim().replace(/\/+$/, "");
}

function readConfigObject(api) {
  if (api?.plugin && typeof api.plugin === "object" && api.plugin.config) {
    return api.plugin.config;
  }
  const entries = api?.config?.plugins?.entries;
  if (entries && typeof entries === "object") {
    const pluginEntry = entries[PLUGIN_ID];
    if (pluginEntry && typeof pluginEntry === "object" && pluginEntry.config) {
      return pluginEntry.config;
    }
  }
  return {};
}

export function resolvePluginConfig(api) {
  const pluginConfig = readConfigObject(api);
  const env = typeof process === "object" ? process.env : {};

  const baseUrl = normalizeBaseUrl(env?.EAP_RUNTIME_BASE_URL ?? pluginConfig.baseUrl);
  const apiKey = env?.EAP_RUNTIME_API_KEY ?? pluginConfig.apiKey;
  const timeoutMs = parseTimeout(env?.EAP_RUNTIME_TIMEOUT_MS ?? pluginConfig.timeoutMs);

  if (!baseUrl) {
    throw new Error("EAP runtime plugin requires `baseUrl` configuration.");
  }

  return {
    baseUrl,
    apiKey: apiKey ? String(apiKey) : undefined,
    timeoutMs,
  };
}

function makeAuthHeaders(apiKey) {
  /** @type {Record<string, string>} */
  const headers = {
    Accept: "application/json",
    "Content-Type": "application/json",
  };
  if (apiKey) {
    headers.Authorization = `Bearer ${apiKey}`;
  }
  return headers;
}

async function parseResponseBody(response) {
  const raw = await response.text();
  if (!raw) {
    return {};
  }
  try {
    return JSON.parse(raw);
  } catch {
    return { message: raw };
  }
}

async function requestJson(fetchImpl, config, method, path, body, timeoutMsOverride) {
  const timeoutMs = parseTimeout(timeoutMsOverride ?? config.timeoutMs);
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetchImpl(`${config.baseUrl}${path}`, {
      method,
      headers: makeAuthHeaders(config.apiKey),
      body: body === undefined ? undefined : JSON.stringify(body),
      signal: controller.signal,
    });
    const parsedBody = await parseResponseBody(response);
    if (!response.ok) {
      const message =
        (parsedBody && typeof parsedBody.message === "string" && parsedBody.message) ||
        `EAP runtime request failed (${response.status}).`;
      const error = new Error(message);
      error.statusCode = response.status;
      error.payload = parsedBody;
      throw error;
    }
    return parsedBody;
  } catch (error) {
    if (error && typeof error === "object" && error.name === "AbortError") {
      throw new Error(`EAP runtime request timed out after ${timeoutMs}ms.`);
    }
    throw error;
  } finally {
    clearTimeout(timer);
  }
}

export function createEAPRuntimeClient(config, fetchImpl = fetch) {
  return {
    async runEapWorkflow(macro, timeoutMs) {
      return requestJson(
        fetchImpl,
        config,
        "POST",
        "/v1/eap/macro/execute",
        { macro },
        timeoutMs,
      );
    },
    async getEapRunStatus(runId, timeoutMs) {
      return requestJson(
        fetchImpl,
        config,
        "GET",
        `/v1/eap/runs/${encodeURIComponent(String(runId))}`,
        undefined,
        timeoutMs,
      );
    },
    async getEapPointerSummary(pointerId, timeoutMs) {
      return requestJson(
        fetchImpl,
        config,
        "GET",
        `/v1/eap/pointers/${encodeURIComponent(String(pointerId))}/summary`,
        undefined,
        timeoutMs,
      );
    },
  };
}

function asToolResult(payload) {
  return {
    content: [
      {
        type: "text",
        text: JSON.stringify(payload, null, 2),
      },
    ],
  };
}

export default function activate(api) {
  const config = resolvePluginConfig(api);
  const client = createEAPRuntimeClient(config);

  api.registerTool(
    "run_eap_workflow",
    {
      description: "Execute an EAP BatchedMacroRequest and return pointer metadata.",
      inputSchema: {
        type: "object",
        properties: {
          macro: {
            type: "object",
            description: "BatchedMacroRequest payload accepted by /v1/eap/macro/execute.",
          },
          requestTimeoutMs: {
            type: "integer",
            minimum: 1000,
            maximum: 120000,
            description: "Optional request timeout override.",
          },
        },
        required: ["macro"],
        additionalProperties: false,
      },
      outputSchema: {
        type: "object",
      },
    },
    async (args) => {
      const result = await client.runEapWorkflow(args.macro, args.requestTimeoutMs);
      return asToolResult(result);
    },
  );

  api.registerTool(
    "get_eap_run_status",
    {
      description: "Fetch run summary and trace events for a specific execution run.",
      inputSchema: {
        type: "object",
        properties: {
          run_id: { type: "string", minLength: 1 },
          requestTimeoutMs: {
            type: "integer",
            minimum: 1000,
            maximum: 120000,
          },
        },
        required: ["run_id"],
        additionalProperties: false,
      },
      outputSchema: {
        type: "object",
      },
    },
    async (args) => {
      const result = await client.getEapRunStatus(args.run_id, args.requestTimeoutMs);
      return asToolResult(result);
    },
  );

  api.registerTool(
    "get_eap_pointer_summary",
    {
      description: "Fetch EAP pointer summary metadata without downloading pointer payload.",
      inputSchema: {
        type: "object",
        properties: {
          pointer_id: { type: "string", minLength: 1 },
          requestTimeoutMs: {
            type: "integer",
            minimum: 1000,
            maximum: 120000,
          },
        },
        required: ["pointer_id"],
        additionalProperties: false,
      },
      outputSchema: {
        type: "object",
      },
    },
    async (args) => {
      const result = await client.getEapPointerSummary(args.pointer_id, args.requestTimeoutMs);
      return asToolResult(result);
    },
  );
}
