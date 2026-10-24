"""Base telemetry adapter interface."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

@dataclass
class TelemetryRecord:
    source: str          # e.g. "prometheus", "jaeger", "opensearch"
    kind: str            # "metric", "log", "trace", "health"
    timestamp: str
    service: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)
    raw: Any = None

class TelemetryAdapter(Protocol):
    name: str
    def health(self) -> bool: ...
    def list_services(self) -> list[str]: ...
    def query_metrics(self, query: str, start: str | None = None, end: str | None = None, step: str = "60s") -> list[TelemetryRecord]: ...
    def query_logs(self, service: str | None = None, severity: str | None = None, trace_id: str | None = None, start: str | None = None, end: str | None = None, limit: int = 100) -> list[TelemetryRecord]: ...
    def query_traces(self, service: str | None = None, start: str | None = None, end: str | None = None, limit: int = 50) -> list[TelemetryRecord]: ...
