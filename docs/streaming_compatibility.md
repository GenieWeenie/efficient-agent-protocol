# Streaming Compatibility Matrix

EAP supports streaming via two API modes: `chat_completions` and `responses`. Streaming behavior depends on the gateway's SSE (Server-Sent Events) support.

## Compatibility Matrix

| Gateway / Provider | `chat_completions` Streaming | `responses` Streaming | Notes |
|---|---|---|---|
| **LM Studio** (v0.3+) | Full support | Not supported | Use `chat_completions` mode |
| **Ollama** (v0.3+) | Full support (via OpenAI compat) | Not supported | Native API also supported via `ollama` provider |
| **OpenAI API** | Full support | Full support | Both modes fully supported |
| **Azure OpenAI** | Full support | Partial (depends on deployment) | Check API version >=2024-02-01 |
| **Anthropic API** | Full support (via provider) | N/A | Uses native Anthropic streaming |
| **Google Gemini** | Full support (via provider) | N/A | Uses native Google streaming |
| **vLLM** | Full support | Not supported | Use `chat_completions` mode |
| **LocalAI** | Full support | Not supported | Use `chat_completions` mode |
| **text-generation-inference** | Full support | Not supported | Use `chat_completions` mode |

## API Mode Selection

Set via `EAP_OPENAI_API_MODE` (or per-role: `EAP_ARCHITECT_OPENAI_API_MODE`):

- **`chat_completions`** (default): Uses `/v1/chat/completions` with `stream: true`. Widest compatibility.
- **`responses`**: Uses `/v1/responses` with `stream: true`. Only supported by OpenAI and compatible gateways.

**Recommendation**: Use `chat_completions` unless you specifically need the Responses API format.

## Known Quirks

### SSE Buffering

Some reverse proxies (nginx, Cloudflare) buffer SSE responses. If streaming appears delayed or arrives in large chunks:

- Disable proxy buffering (`proxy_buffering off` in nginx)
- Set `X-Accel-Buffering: no` header
- Reduce proxy buffer sizes

### Responses API Gateway Support

The `/v1/responses` endpoint is an OpenAI-specific API path. Most local model servers do not support it. When using `responses` mode against an unsupported gateway, EAP will raise:

```
RuntimeError: OpenAI Responses API path is unavailable on this endpoint.
```

**Fix**: Switch to `chat_completions` mode or upgrade your gateway.

### Partial Stream Recovery

If a stream disconnects mid-response, EAP's `stream_chat()` method will:
1. Attempt to fall back to a non-streaming completion (if `fallback_to_non_stream=True`)
2. Deduplicate content that was already streamed
3. Emit the remaining content via the `on_token` callback

This provides graceful degradation but means the response may arrive with a pause.

### Timeout Behavior

Streaming requests use the same `timeout_seconds` as non-streaming requests. For long-running streaming responses, increase `EAP_TIMEOUT_SECONDS` (or the per-role variant). The timeout applies to the initial connection, not to the total stream duration.

## Testing Streaming

Run the streaming integration tests:

```bash
PYTHONPATH=. pytest tests/integration/test_streaming.py -v
PYTHONPATH=. pytest tests/integration/test_openai_responses_streaming.py -v
```

For manual testing against a live gateway:

```python
from eap.agent import AgentClient

client = AgentClient(
    base_url="http://localhost:1234",
    model_name="your-model",
    openai_api_mode="chat_completions",
)
result = client.stream_chat("Hello, world!", on_token=lambda t: print(t, end="", flush=True))
print()
```
