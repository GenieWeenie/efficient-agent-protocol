import json
from typing import Dict, Iterable

import requests

from .base import CompletionRequest, CompletionResponse, LLMProvider


class OpenAIProvider(LLMProvider):
    """Adapter for OpenAI-compatible `/v1/chat/completions` APIs."""

    def __init__(self, endpoint: str, api_key: str, timeout_seconds: int):
        self.endpoint = endpoint
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds

    def _headers(self) -> Dict[str, str]:
        if self.api_key and self.api_key != "not-needed":
            return {"Authorization": f"Bearer {self.api_key}"}
        return {}

    def _request(self, request: CompletionRequest) -> CompletionResponse:
        payload = {
            "model": request.model,
            "messages": [{"role": msg.role, "content": msg.content} for msg in request.messages],
            "temperature": request.temperature,
        }
        if request.tools:
            payload["tools"] = request.tools

        response = requests.post(
            self.endpoint,
            json=payload,
            headers=self._headers(),
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        raw_json = response.json()
        return CompletionResponse(
            text=raw_json["choices"][0]["message"]["content"],
            raw_response=raw_json,
        )

    def complete(self, request: CompletionRequest) -> CompletionResponse:
        return self._request(request)

    def complete_with_tools(self, request: CompletionRequest) -> CompletionResponse:
        return self._request(request)

    def stream(self, request: CompletionRequest) -> Iterable[str]:
        payload = {
            "model": request.model,
            "messages": [{"role": msg.role, "content": msg.content} for msg in request.messages],
            "temperature": request.temperature,
            "stream": True,
        }
        if request.tools:
            payload["tools"] = request.tools

        response = requests.post(
            self.endpoint,
            json=payload,
            headers=self._headers(),
            timeout=self.timeout_seconds,
            stream=True,
        )
        response.raise_for_status()
        for raw_line in response.iter_lines():
            if not raw_line:
                continue
            line = raw_line.decode("utf-8")
            if not line.startswith("data:"):
                continue
            data = line[len("data:") :].strip()
            if data == "[DONE]":
                break
            try:
                payload_obj = json.loads(data)
            except json.JSONDecodeError:
                continue
            token = (
                payload_obj.get("choices", [{}])[0]
                .get("delta", {})
                .get("content")
            )
            if token:
                yield str(token)
