import json
from typing import Dict, Iterable, Optional, Tuple

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

    @staticmethod
    def _extract_responses_stream_token(payload_obj: Dict[str, object]) -> Tuple[Optional[str], bool]:
        event_type = payload_obj.get("type")
        if event_type == "response.error":
            error_obj = payload_obj.get("error")
            message = "Responses stream returned an error event."
            if isinstance(error_obj, dict):
                error_message = error_obj.get("message")
                if isinstance(error_message, str) and error_message:
                    message = error_message
                error_code = error_obj.get("code")
                if isinstance(error_code, str) and error_code:
                    message = f"{message} (code={error_code})"
            raise RuntimeError(message)

        if event_type == "response.output_text.delta":
            delta = payload_obj.get("delta")
            if isinstance(delta, str) and delta:
                return delta, True
            text = payload_obj.get("text")
            if isinstance(text, str) and text:
                return text, True

        if event_type == "response.output_text.done":
            text = payload_obj.get("text")
            if isinstance(text, str) and text:
                return text, False

        if event_type == "response.completed":
            response_obj = payload_obj.get("response")
            if isinstance(response_obj, dict):
                try:
                    return OpenAIProvider._extract_responses_text(response_obj), False
                except KeyError:
                    return None, False

        choices = payload_obj.get("choices")
        if isinstance(choices, list) and choices:
            first_choice = choices[0]
            if isinstance(first_choice, dict):
                delta_obj = first_choice.get("delta")
                if isinstance(delta_obj, dict):
                    content = delta_obj.get("content")
                    if isinstance(content, str) and content:
                        return content, True

        output = payload_obj.get("output")
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
                    if not isinstance(text, str) or not text:
                        continue
                    block_type = block.get("type")
                    if block_type == "output_text.delta":
                        return text, True
                    if block_type in {"output_text", "text"}:
                        return text, False

        output_text = payload_obj.get("output_text")
        if isinstance(output_text, str) and output_text:
            return output_text, False

        return None, False

    def stream(self, request: CompletionRequest) -> Iterable[str]:
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
                "stream": True,
            }
            if request.tools:
                payload["tools"] = request.tools

            try:
                response = requests.post(
                    self.endpoint,
                    json=payload,
                    headers=self._headers(),
                    timeout=self.timeout_seconds,
                    stream=True,
                )
            except requests.ConnectionError as exc:
                raise RuntimeError(
                    f"Failed to connect to responses streaming endpoint ({self.endpoint}). "
                    f"Verify the gateway is running and supports the /v1/responses path. "
                    f"See docs/streaming_compatibility.md for supported gateways."
                ) from exc
            except requests.Timeout as exc:
                raise RuntimeError(
                    f"Timeout connecting to responses streaming endpoint ({self.endpoint}). "
                    f"Consider increasing EAP_TIMEOUT_SECONDS (current: {self.timeout_seconds}s)."
                ) from exc
            try:
                response.raise_for_status()
            except requests.HTTPError as exc:
                if response.status_code in {404, 405, 410, 501}:
                    raise RuntimeError(
                        f"OpenAI Responses API path is unavailable on this endpoint ({self.endpoint}). "
                        f"Switch to chat_completions mode or use a compatible gateway. "
                        f"See docs/streaming_compatibility.md."
                    ) from exc
                raise

            saw_incremental = False
            emitted_final_fallback = False
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
                if not isinstance(payload_obj, dict):
                    continue

                token, is_incremental = self._extract_responses_stream_token(payload_obj)
                if not token:
                    continue
                if is_incremental:
                    saw_incremental = True
                    yield token
                    continue
                if saw_incremental or emitted_final_fallback:
                    continue
                emitted_final_fallback = True
                yield token
            return

        payload = {
            "model": request.model,
            "messages": [{"role": msg.role, "content": msg.content} for msg in request.messages],
            "temperature": request.temperature,
            "stream": True,
        }
        if request.tools:
            payload["tools"] = request.tools

        try:
            response = requests.post(
                self.endpoint,
                json=payload,
                headers=self._headers(),
                timeout=self.timeout_seconds,
                stream=True,
            )
        except requests.ConnectionError as exc:
            raise RuntimeError(
                f"Failed to connect to streaming endpoint ({self.endpoint}). "
                f"Verify the gateway is running and reachable."
            ) from exc
        except requests.Timeout as exc:
            raise RuntimeError(
                f"Timeout connecting to streaming endpoint ({self.endpoint}). "
                f"Consider increasing EAP_TIMEOUT_SECONDS (current: {self.timeout_seconds}s)."
            ) from exc
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
