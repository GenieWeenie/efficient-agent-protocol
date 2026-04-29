"""Ollama provider adapter for EAP.

Connects to the Ollama REST API (``/api/chat``) which uses a different
request/response format than the OpenAI-compatible endpoint.  This
provider talks directly to Ollama's native API rather than requiring
Ollama's OpenAI-compatibility shim.
"""
import json
from typing import Dict, Iterable, Optional

import requests

from .base import CompletionRequest, CompletionResponse, LLMProvider


DEFAULT_OLLAMA_BASE_URL = "http://localhost:11434"


class OllamaProvider(LLMProvider):
    """Provider for the Ollama native REST API."""

    def __init__(
        self,
        base_url: str = DEFAULT_OLLAMA_BASE_URL,
        timeout_seconds: int = 120,
        extra_headers: Optional[Dict[str, str]] = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.extra_headers = dict(extra_headers or {})

    def _headers(self) -> Dict[str, str]:
        headers = {"Content-Type": "application/json"}
        headers.update(self.extra_headers)
        return headers

    def _build_messages(self, request: CompletionRequest) -> list:
        return [{"role": msg.role, "content": msg.content} for msg in request.messages]

    def complete(self, request: CompletionRequest) -> CompletionResponse:
        payload = {
            "model": request.model,
            "messages": self._build_messages(request),
            "stream": False,
            "options": {"temperature": request.temperature},
        }
        response = requests.post(
            f"{self.base_url}/api/chat",
            json=payload,
            headers=self._headers(),
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        raw_json = response.json()
        text = raw_json.get("message", {}).get("content", "")
        return CompletionResponse(text=text, raw_response=raw_json)

    def complete_with_tools(self, request: CompletionRequest) -> CompletionResponse:
        return self.complete(request)

    def stream(self, request: CompletionRequest) -> Iterable[str]:
        payload = {
            "model": request.model,
            "messages": self._build_messages(request),
            "stream": True,
            "options": {"temperature": request.temperature},
        }
        response = requests.post(
            f"{self.base_url}/api/chat",
            json=payload,
            headers=self._headers(),
            timeout=self.timeout_seconds,
            stream=True,
        )
        response.raise_for_status()
        for raw_line in response.iter_lines():
            if not raw_line:
                continue
            try:
                chunk = json.loads(raw_line.decode("utf-8"))
            except json.JSONDecodeError:
                continue
            if not isinstance(chunk, dict):
                continue
            content = chunk.get("message", {}).get("content")
            if content:
                yield str(content)
            if chunk.get("done", False):
                break
