from typing import Dict, List
from urllib.parse import quote

import requests

from .base import CompletionRequest, CompletionResponse, LLMProvider


class GoogleProvider(LLMProvider):
    """Adapter for Google Gemini generateContent API."""

    def __init__(self, base_url: str, api_key: str, timeout_seconds: int):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds

    def _endpoint_for_model(self, model: str) -> str:
        return f"{self.base_url}/models/{quote(model, safe='')}:generateContent"

    @staticmethod
    def _to_google_tools(tools: List[Dict[str, object]]) -> List[Dict[str, object]]:
        declarations = []
        for tool in tools:
            if tool.get("type") == "function":
                function_body = tool.get("function", {})
                if isinstance(function_body, dict):
                    declarations.append(function_body)
        if not declarations:
            return []
        return [{"functionDeclarations": declarations}]

    def _to_payload(self, request: CompletionRequest) -> Dict[str, object]:
        system_chunks = []
        contents = []
        for msg in request.messages:
            if msg.role == "system":
                system_chunks.append(msg.content)
                continue
            role = "model" if msg.role == "assistant" else "user"
            contents.append({"role": role, "parts": [{"text": msg.content}]})

        payload: Dict[str, object] = {
            "contents": contents,
            "generationConfig": {"temperature": request.temperature},
        }
        if system_chunks:
            payload["systemInstruction"] = {"parts": [{"text": "\n\n".join(system_chunks)}]}
        if request.tools:
            google_tools = self._to_google_tools(request.tools)
            if google_tools:
                payload["tools"] = google_tools
        return payload

    @staticmethod
    def _extract_text(raw_json: Dict[str, object]) -> str:
        candidates = raw_json.get("candidates", [])
        if not isinstance(candidates, list) or not candidates:
            return ""
        first = candidates[0]
        if not isinstance(first, dict):
            return ""
        content = first.get("content", {})
        if not isinstance(content, dict):
            return ""
        parts = content.get("parts", [])
        if not isinstance(parts, list):
            return ""
        return "".join(str(part.get("text", "")) for part in parts if isinstance(part, dict))

    def _request(self, request: CompletionRequest) -> CompletionResponse:
        endpoint = self._endpoint_for_model(request.model)
        response = requests.post(
            endpoint,
            params={"key": self.api_key},
            json=self._to_payload(request),
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
        raise NotImplementedError("Streaming not implemented for GoogleProvider yet.")
