"""Prometheus adapter."""
from __future__ import annotations

import httpx
from datetime import datetime, timezone

from eyes_core.config import PROMETHEUS_BASE
from .base import TelemetryAdapter, TelemetryRecord

class PrometheusAdapter:
    name = "prometheus"

    def __init__(self, base_url: str | None = None, timeout: float = 10.0):
        self.base = (base_url or PROMETHEUS_BASE).rstrip("/")
        self.timeout = timeout

    def _c(self):
        return httpx.Client(base_url=self.base, timeout=self.timeout)

    def health(self) -> bool:
        try:
            with self._c() as c:
                r = c.get("/-/healthy")
                return r.status_code < 400
        except Exception:
            return False

    def list_services(self) -> list[str]:
        # Prometheus doesn't track service list directly; return label values for service.name
        try:
            with self._c() as c:
                r = c.get("/api/v1/label/service_name/values")
                r.raise_for_status()
                return r.json().get("data", [])
        except Exception:
            return []

    def query_instant(self, query: str) -> list[TelemetryRecord]:
        try:
            with self._c() as c:
                r = c.get("/api/v1/query", params={"query": query})
                r.raise_for_status()
                data = r.json().get("data", {}).get("result", [])
        except Exception:
            return []
        out = []
        for item in data:
            ts = item.get("value", [None, None])[0]
            val = item.get("value", [None, None])[1]
            labels = item.get("metric", {})
            out.append(TelemetryRecord(
                source="prometheus", kind="metric",
                timestamp=str(ts), service=labels.get("service_name") or labels.get("service"),
                payload={"query": query, "value": val, "labels": labels},
            ))
        return out

    def query_metrics(self, query, start=None, end=None, step="60s"):
        if start and end:
            try:
                with self._c() as c:
                    r = c.get("/api/v1/query_range", params={"query": query, "start": start, "end": end, "step": step})
                    r.raise_for_status()
                    data = r.json().get("data", {}).get("result", [])
            except Exception:
                return []
            out = []
            for item in data:
                labels = item.get("metric", {})
                for ts, val in item.get("values", []):
                    out.append(TelemetryRecord(
                        source="prometheus", kind="metric", timestamp=str(ts),
                        service=labels.get("service_name") or labels.get("service"),
                        payload={"query": query, "value": val, "labels": labels},
                    ))
            return out
        return self.query_instant(query)

    def query_logs(self, *a, **k):
        return []

    def query_traces(self, *a, **k):
        return []
