import json
from typing import Dict, Iterable, Optional

import requests

from .base import CompletionRequest, CompletionResponse, LLMProvider


class OpenAIProvider(LLMProvider):
    """Adapter for OpenAI-compatible APIs (`/v1/chat/completions` and `/v1/responses`)."""

    def __init__(
        self,
        endpoint: str,
        api_key: str,
        timeout_seconds: int,
        extra_headers: Optional[Dict[str, str]] = None,
        api_mode: str = "chat_completions",
    ):
        self.endpoint = endpoint
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds
        self.extra_headers = dict(extra_headers or {})
        self.api_mode = api_mode

    def _headers(self) -> Dict[str, str]:
        headers = dict(self.extra_headers)
        if self.api_key and self.api_key != "not-needed":
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def _request(self, request: CompletionRequest) -> CompletionResponse:
        if self.api_mode == "responses":
            payload = {
                "model": request.model,
                "input": [
                    {
                        "role": msg.role,
                        "content": [{"type": "text", "text": msg.content}],
                    }
                    for msg in request.messages
                ],
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
            try:
                response.raise_for_status()
            except requests.HTTPError as exc:
                if response.status_code in {404, 405, 410, 501}:
                    raise RuntimeError(
                        "OpenAI Responses API path is unavailable on this endpoint."
                    ) from exc
                raise
            raw_json = response.json()
            return CompletionResponse(
                text=self._extract_responses_text(raw_json),
                raw_response=raw_json,
            )

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

    @staticmethod
    def _extract_responses_text(raw_json: Dict[str, object]) -> str:
        output_text = raw_json.get("output_text")
        if isinstance(output_text, str) and output_text:
            return output_text

        fragments = []
        output = raw_json.get("output")
        if isinstance(output, list):
            for item in output:
                if not isinstance(item, dict):
                    continue
                content = item.get("content")
                if not isinstance(content, list):
                    continue
                for block in content:
                    if not isinstance(block, dict):
                        continue
                    text = block.get("text")
                    if isinstance(text, str) and text:
                        fragments.append(text)
        if fragments:
            return "".join(fragments)
        raise KeyError("Responses payload did not include output_text content.")

    def complete(self, request: CompletionRequest) -> CompletionResponse:
        return self._request(request)

    def complete_with_tools(self, request: CompletionRequest) -> CompletionResponse:
        return self._request(request)

    def stream(self, request: CompletionRequest) -> Iterable[str]:
        if self.api_mode == "responses":
            raise NotImplementedError("Streaming is not implemented for responses API mode.")

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
