from typing import Dict, Optional

from .anthropic_provider import AnthropicProvider
from .base import LLMProvider
from .google_provider import GoogleProvider
from .openai_provider import OpenAIProvider


DEFAULT_GOOGLE_BASE_URL = "https://generativelanguage.googleapis.com/v1beta"
DEFAULT_ANTHROPIC_BASE_URL = "https://api.anthropic.com"


def _normalize_provider_name(provider_name: str) -> str:
    return (provider_name or "local").strip().lower()


def _normalize_openai_api_mode(openai_api_mode: str) -> str:
    normalized = (openai_api_mode or "chat_completions").strip().lower()
    if normalized in {"chat_completions", "responses"}:
        return normalized
    raise ValueError(f"Unsupported OpenAI API mode: {openai_api_mode}")


def _build_provider(
    provider_name: str,
    base_url: str,
    api_key: str,
    timeout_seconds: int,
    extra_headers: Optional[Dict[str, str]] = None,
    openai_api_mode: str = "chat_completions",
) -> LLMProvider:
    normalized = _normalize_provider_name(provider_name)
    if normalized in {"local", "openai"}:
        normalized_api_mode = _normalize_openai_api_mode(openai_api_mode)
        if normalized_api_mode == "responses":
            endpoint = f"{base_url.rstrip('/')}/v1/responses"
        else:
            endpoint = f"{base_url.rstrip('/')}/v1/chat/completions"
        return OpenAIProvider(
            endpoint=endpoint,
            api_key=api_key,
            timeout_seconds=timeout_seconds,
            extra_headers=extra_headers,
            api_mode=normalized_api_mode,
        )

    if normalized == "anthropic":
        if not api_key or api_key == "not-needed":
            raise ValueError("anthropic provider requires a valid API key")
        resolved_base = base_url.rstrip("/") if base_url else DEFAULT_ANTHROPIC_BASE_URL
        endpoint = f"{resolved_base}/v1/messages"
        return AnthropicProvider(endpoint=endpoint, api_key=api_key, timeout_seconds=timeout_seconds)

    if normalized == "google":
        if not api_key or api_key == "not-needed":
            raise ValueError("google provider requires a valid API key")
        resolved_base = base_url.rstrip("/") if base_url else DEFAULT_GOOGLE_BASE_URL
        return GoogleProvider(base_url=resolved_base, api_key=api_key, timeout_seconds=timeout_seconds)

    raise ValueError(f"Unsupported provider: {provider_name}")


def create_provider(
    provider_name: str,
    base_url: str,
    api_key: str,
    timeout_seconds: int,
    fallback_provider_name: Optional[str] = None,
    extra_headers: Optional[Dict[str, str]] = None,
    openai_api_mode: str = "chat_completions",
) -> LLMProvider:
    try:
        return _build_provider(
            provider_name=provider_name,
            base_url=base_url,
            api_key=api_key,
            timeout_seconds=timeout_seconds,
            extra_headers=extra_headers,
            openai_api_mode=openai_api_mode,
        )
    except ValueError:
        if not fallback_provider_name:
            raise
        return _build_provider(
            provider_name=fallback_provider_name,
            base_url=base_url,
            api_key=api_key,
            timeout_seconds=timeout_seconds,
            extra_headers=extra_headers,
            openai_api_mode=openai_api_mode,
        )
