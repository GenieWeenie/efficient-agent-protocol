from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional


@dataclass(frozen=True)
class ProviderMessage:
    role: str
    content: str


@dataclass(frozen=True)
class CompletionRequest:
    model: str
    messages: List[ProviderMessage]
    temperature: float = 0.0
    tools: Optional[List[Dict[str, Any]]] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CompletionResponse:
    text: str
    raw_response: Optional[Dict[str, Any]] = None


class LLMProvider(ABC):
    """Provider abstraction used by AgentClient for chat and macro planning."""

    @abstractmethod
    def complete(self, request: CompletionRequest) -> CompletionResponse:
        """Run a standard completion call and return normalized text output."""

    @abstractmethod
    def complete_with_tools(self, request: CompletionRequest) -> CompletionResponse:
        """Run a completion call in tool-planning mode and return normalized text output."""

    @abstractmethod
    def stream(self, request: CompletionRequest) -> Iterable[str]:
        """Stream completion tokens/chunks for providers that support streaming."""
