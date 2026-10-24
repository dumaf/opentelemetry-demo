"""Telemetry adapter registry and availability."""
from __future__ import annotations

from .adapters.prometheus import PrometheusAdapter
from .adapters.jaeger import JaegerAdapter
from .adapters.opensearch import OpenSearchAdapter
from .adapters.base import TelemetryRecord

ADAPTERS = {
    "prometheus": PrometheusAdapter,
    "jaeger": JaegerAdapter,
    "opensearch": OpenSearchAdapter,
}

def availability() -> dict[str, bool]:
    out = {}
    for name, cls in ADAPTERS.items():
        try:
            out[name] = cls().health()
        except Exception:
            out[name] = False
    return out

def get(name: str):
    cls = ADAPTERS.get(name)
    return cls() if cls else None
