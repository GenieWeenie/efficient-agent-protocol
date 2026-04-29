from typing import Dict, List

import requests

from .base import CompletionRequest, CompletionResponse, LLMProvider


class AnthropicProvider(LLMProvider):
    """Adapter for Anthropic `/v1/messages` APIs."""

    def __init__(self, endpoint: str, api_key: str, timeout_seconds: int):
        self.endpoint = endpoint
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds

    def _headers(self) -> Dict[str, str]:
        return {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }

    def _to_payload(self, request: CompletionRequest) -> Dict[str, object]:
        system_chunks: List[str] = []
        messages = []
        for msg in request.messages:
            if msg.role == "system":
                system_chunks.append(msg.content)
            else:
                role = "assistant" if msg.role == "assistant" else "user"
                messages.append({"role": role, "content": msg.content})

        payload: Dict[str, object] = {
            "model": request.model,
            "messages": messages,
            "temperature": request.temperature,
            "max_tokens": int(request.metadata.get("max_tokens", 1024)),
        }
        if system_chunks:
            payload["system"] = "\n\n".join(system_chunks)
        if request.tools:
            payload["tools"] = request.tools
        return payload

    def _extract_text(self, raw_json: Dict[str, object]) -> str:
        content = raw_json.get("content", [])
        if isinstance(content, list):
            text_parts = []
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text":
                    text_parts.append(str(item.get("text", "")))
            return "".join(text_parts)
        return ""

    def _request(self, request: CompletionRequest) -> CompletionResponse:
        response = requests.post(
            self.endpoint,
            json=self._to_payload(request),
            headers=self._headers(),
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        raw_json = response.json()
        return CompletionResponse(text=self._extract_text(raw_json), raw_response=raw_json)

    def complete(self, request: CompletionRequest) -> CompletionResponse:
        return self._request(request)

    def complete_with_tools(self, request: CompletionRequest) -> CompletionResponse:
        return self._request(request)

    def stream(self, request: CompletionRequest):
        raise NotImplementedError("Streaming not implemented for AnthropicProvider yet.")
