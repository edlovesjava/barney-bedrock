"""Model adapter interface.

The harness keeps the conversation as a list of ``Message`` objects. Assistant
messages carry the provider-native content blocks verbatim (``raw``) so that
reasoning blocks and other provider extras are replayed exactly; the parsed
``text`` and ``tool_calls`` are convenience views.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    input: dict[str, Any]


@dataclass(frozen=True)
class ToolResult:
    tool_call_id: str
    content: str
    is_error: bool = False


@dataclass(frozen=True)
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0

    def __add__(self, other: Usage) -> Usage:
        return Usage(
            self.input_tokens + other.input_tokens,
            self.output_tokens + other.output_tokens,
            self.cache_read_tokens + other.cache_read_tokens,
            self.cache_write_tokens + other.cache_write_tokens,
        )


@dataclass
class Message:
    role: str  # "user" | "assistant"
    text: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    tool_results: list[ToolResult] = field(default_factory=list)
    raw: Any = None  # provider-native content for assistant turns; replayed verbatim


@dataclass(frozen=True)
class Completion:
    message: Message
    stop_reason: str  # end_turn | tool_use | max_tokens | other
    usage: Usage
    latency_s: float


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    schema: dict[str, Any]


class ModelAdapter(Protocol):
    model_id: str

    def complete(self, system: str, messages: list[Message], tools: list[ToolSpec], max_tokens: int) -> Completion: ...
