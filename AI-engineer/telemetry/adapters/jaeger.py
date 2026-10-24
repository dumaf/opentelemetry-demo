"""Jaeger adapter."""
from __future__ import annotations

import httpx

from eyes_core.config import JAEGER_BASE
from .base import TelemetryRecord

class JaegerAdapter:
    name = "jaeger"

    def __init__(self, base_url: str | None = None, timeout: float = 10.0):
        self.base = (base_url or JAEGER_BASE).rstrip("/")
        self.timeout = timeout

    def _c(self):
        return httpx.Client(base_url=self.base, timeout=self.timeout)

    def health(self) -> bool:
        try:
            with self._c() as c:
                r = c.get("/api/services")
                return r.status_code < 400
        except Exception:
            return False

    def list_services(self) -> list[str]:
        try:
            with self._c() as c:
                r = c.get("/api/services")
                r.raise_for_status()
                return r.json().get("data", [])
        except Exception:
            return []

    def query_traces(self, service=None, start=None, end=None, limit=50, **kw):
        params = {"limit": limit}
        if service:
            params["service"] = service
        if start:
            params["start"] = start
        if end:
            params["end"] = end
        try:
            with self._c() as c:
                r = c.get("/api/traces", params=params)
                r.raise_for_status()
                data = r.json().get("data", [])
        except Exception:
            return []
        out = []
        for t in data:
            trace_id = t.get("traceID")
            spans = t.get("spans", [])
            has_error = any(s.get("tags", []) and any(tag.get("key") == "error" and tag.get("value") for tag in s.get("tags", [])) for s in spans)
            out.append(TelemetryRecord(
                source="jaeger", kind="trace", timestamp=str(t.get("startTime", "")),
                service=service,
                payload={"trace_id": trace_id, "span_count": len(spans), "has_error": has_error, "spans": spans},
                raw=t,
            ))
        return out

    def get_trace(self, trace_id: str):
        try:
            with self._c() as c:
                r = c.get(f"/api/traces/{trace_id}")
                r.raise_for_status()
                return r.json().get("data", [])
        except Exception:
            return []

    def query_metrics(self, *a, **k):
        return []

    def query_logs(self, *a, **k):
        return []
