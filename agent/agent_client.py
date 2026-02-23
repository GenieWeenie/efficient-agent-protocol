# agent/agent_client.py
import json
from typing import Callable, Dict, Any, Optional
from .compiler import MacroCompiler
from .providers import CompletionRequest, LLMProvider, ProviderMessage, create_provider
from protocol.models import BatchedMacroRequest


class AgentClient:
    def __init__(
        self,
        base_url: str,
        model_name: str,
        api_key: str = "not-needed",
        system_prompt: str = "",
        temperature: float = 0.0,
        timeout_seconds: int = 60,
        provider_name: str = "local",
        fallback_provider_name: Optional[str] = None,
        provider: Optional[LLMProvider] = None,
    ):
        self.endpoint = f"{base_url.rstrip('/')}/v1/chat/completions"
        self.base_url = base_url.rstrip("/")
        self.model_name = model_name
        self.api_key = api_key
        self.system_prompt = system_prompt
        self.temperature = temperature
        self.timeout_seconds = timeout_seconds
        self.provider_name = provider_name
        self.fallback_provider_name = fallback_provider_name
        self.provider = provider or create_provider(
            provider_name=provider_name,
            base_url=self.base_url,
            api_key=api_key,
            timeout_seconds=timeout_seconds,
            fallback_provider_name=fallback_provider_name,
        )
        self.compiler = MacroCompiler()

    def _headers(self) -> Dict[str, str]:
        if hasattr(self.provider, "_headers"):
            return self.provider._headers()  # type: ignore[attr-defined]
        if self.api_key and self.api_key != "not-needed":
            return {"Authorization": f"Bearer {self.api_key}"}
        return {}

    def chat(self, user_input: str) -> str:
        """Simple text-to-text chat for non-macro tasks like auditing."""
        request = CompletionRequest(
            model=self.model_name,
            messages=[
                ProviderMessage(role="system", content=self.system_prompt),
                ProviderMessage(role="user", content=user_input),
            ],
            temperature=self.temperature,
        )
        response = self.provider.complete(request)
        return response.text

    def stream_chat(
        self,
        user_input: str,
        on_token: Optional[Callable[[str], None]] = None,
        fallback_to_non_stream: bool = True,
    ) -> str:
        """Stream chat tokens and return the final assembled content.

        If streaming fails and `fallback_to_non_stream` is true, falls back to a
        standard completion request and emits the remaining content.
        """
        request = CompletionRequest(
            model=self.model_name,
            messages=[
                ProviderMessage(role="system", content=self.system_prompt),
                ProviderMessage(role="user", content=user_input),
            ],
            temperature=self.temperature,
        )
        chunks = []
        try:
            for token in self.provider.stream(request):
                if not token:
                    continue
                chunks.append(token)
                if on_token:
                    on_token(token)
        except Exception:
            if not fallback_to_non_stream:
                raise
            fallback_text = self.provider.complete(request).text
            streamed_text = "".join(chunks)
            if streamed_text and fallback_text.startswith(streamed_text):
                remaining = fallback_text[len(streamed_text) :]
            else:
                remaining = fallback_text if not streamed_text else fallback_text
            if remaining:
                chunks.append(remaining)
                if on_token:
                    on_token(remaining)
        return "".join(chunks)

    def generate_macro(
        self,
        user_input: str,
        hashed_manifest: Dict[str, Any],
        error_feedback: str = None,
        memory_context: str = "",
    ) -> BatchedMacroRequest:
        manifest_str = json.dumps(hashed_manifest, indent=2)
        protocol_instructions = (
            "### ENVIRONMENT MANIFEST ###\n"
            f"{manifest_str}\n\n"
            "### SYSTEM RULES ###\n"
            "1. Output ONLY a JSON object. No conversational text.\n"
            "2. Use the exact key names: 'steps', 'step_id', 'tool_name', 'arguments'.\n"
            "3. Use the hashed IDs for 'tool_name'.\n"
        )
        memory_block = f"\n\n### MEMORY CONTEXT ###\n{memory_context}" if memory_context else ""
        error_block = f"\n\n### FIX PREVIOUS ERROR ###\n{error_feedback}" if error_feedback else ""
        
        request = CompletionRequest(
            model=self.model_name,
            messages=[
                ProviderMessage(role="system", content=f"{self.system_prompt}\n\n{protocol_instructions}"),
                ProviderMessage(role="user", content=f"{user_input}{memory_block}{error_block}"),
            ],
            temperature=self.temperature,
        )
        response = self.provider.complete_with_tools(request)
        raw_text = response.text
        return self.compiler.compile(raw_text)
