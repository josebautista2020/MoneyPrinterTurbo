"""Provider-neutral execution contracts for Content Studio AI."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Protocol, runtime_checkable


@dataclass(frozen=True, slots=True)
class ExecutionRequest:
    """A provider-neutral request sent to a rendering engine."""

    request_id: str
    subject: str
    script: str = ""
    options: Mapping[str, Any] = field(default_factory=dict)
    stop_at: str = "video"

    def __post_init__(self) -> None:
        if not self.request_id.strip():
            raise ValueError("request_id must not be empty")
        if not self.subject.strip():
            raise ValueError("subject must not be empty")
        if self.stop_at not in {"script", "terms", "audio", "subtitle", "materials", "video"}:
            raise ValueError(f"unsupported stop_at stage: {self.stop_at}")


@dataclass(frozen=True, slots=True)
class ExecutionResult:
    """Normalized result returned by any rendering engine."""

    request_id: str
    engine: str
    success: bool
    artifacts: tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)
    error: str | None = None


@runtime_checkable
class RenderingEngine(Protocol):
    """Contract implemented by rendering-engine adapters."""

    @property
    def engine_name(self) -> str:
        ...

    def render(self, request: ExecutionRequest) -> ExecutionResult:
        ...
