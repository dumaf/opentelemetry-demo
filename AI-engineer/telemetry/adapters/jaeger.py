"""Jaeger adapter with v2/v3 API fallback."""
from __future__ import annotations

import httpx

from eyes_core.config import JAEGER_BASE
from .base import TelemetryRecord

class JaegerAdapter:
    name = "jaeger"

    def __init__(self, base_url: str | None = None, timeout: float = 10.0):
        self.base = (base_url or JAEGER_BASE).rstrip("/")
        self.timeout = timeout
        self._api_version: str | None = None

    def _c(self):
        return httpx.Client(base_url=self.base, timeout=self.timeout)

    def _detect_api_version(self) -> str | None:
        if self._api_version is not None:
            return self._api_version
        with self._c() as c:
            for ver, path in [("v3", "/api/v3/services"), ("v1", "/api/services")]:
                try:
                    r = c.get(path)
                    if r.status_code < 400:
                        self._api_version = ver
                        return ver
                except Exception:
                    continue
        return None

    def health(self) -> bool:
        try:
            return self._detect_api_version() is not None
        except Exception:
            return False

    def _services_path(self) -> str:
        ver = self._detect_api_version()
        if ver == "v3":
            return "/api/v3/services"
        return "/api/services"

    def list_services(self) -> list[str]:
        try:
            with self._c() as c:
                r = c.get(self._services_path())
                r.raise_for_status()
                data = r.json()
                return data.get("data", data.get("services", []))
        except Exception:
            return []

    def query_traces(self, service=None, start=None, end=None, limit=50, **kw):
        ver = self._detect_api_version()
        if ver == "v3":
            return self._query_traces_v3(service, start, end, limit)
        return self._query_traces_v1(service, start, end, limit)

    def _query_traces_v1(self, service, start, end, limit):
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
        return self._parse_traces(data, service)

    def _query_traces_v3(self, service, start, end, limit):
        params: dict = {}
        query_parts = []
        if service:
            query_parts.append(f'service.name="{service}"')
        if start:
            params["start_time_min"] = start
        if end:
            params["start_time_max"] = end
        if query_parts:
            params["query"] = " && ".join(query_parts)
        params["limit"] = limit
        try:
            with self._c() as c:
                r = c.get("/api/v3/traces", params=params)
                r.raise_for_status()
                body = r.json()
                data = body.get("result", body.get("resourceSpans", body.get("data", [])))
                if isinstance(data, dict):
                    data = data.get("resourceSpans", [])
        except Exception:
            try:
                return self._query_traces_v1(service, start, end, limit)
            except Exception:
                return []
        if not data:
            try:
                return self._query_traces_v1(service, start, end, limit)
            except Exception:
                return []
        out = []
        for rs in data[:limit]:
            spans = []
            for scope_spans in rs.get("scopeSpans", rs.get("instrumentationLibrarySpans", [])):
                spans.extend(scope_spans.get("spans", []))
            trace_id = spans[0].get("traceId", "") if spans else ""
            has_error = any(
                s.get("status", {}).get("code") == 2 or
                any(a.get("key") == "error" and a.get("value", {}).get("boolValue", False)
                    for a in s.get("attributes", []))
                for s in spans
            )
            out.append(TelemetryRecord(
                source="jaeger", kind="trace",
                timestamp=spans[0].get("startTimeUnixNano", "") if spans else "",
                service=service,
                payload={"trace_id": trace_id, "span_count": len(spans), "has_error": has_error, "spans": spans[:10]},
                raw=rs,
            ))
        return out

    def _parse_traces(self, data, service):
        out = []
        for t in data:
            trace_id = t.get("traceID")
            spans = t.get("spans", [])
            has_error = any(
                s.get("tags", []) and any(
                    tag.get("key") == "error" and tag.get("value")
                    for tag in s.get("tags", [])
                )
                for s in spans
            )
            out.append(TelemetryRecord(
                source="jaeger", kind="trace", timestamp=str(t.get("startTime", "")),
                service=service,
                payload={"trace_id": trace_id, "span_count": len(spans), "has_error": has_error, "spans": spans[:10]},
                raw=t,
            ))
        return out

    def get_trace(self, trace_id: str):
        ver = self._detect_api_version()
        path = f"/api/v3/traces/{trace_id}" if ver == "v3" else f"/api/traces/{trace_id}"
        try:
            with self._c() as c:
                r = c.get(path)
                r.raise_for_status()
                return r.json().get("data", r.json().get("result", []))
        except Exception:
            if ver == "v3":
                try:
                    with self._c() as c:
                        r = c.get(f"/api/traces/{trace_id}")
                        r.raise_for_status()
                        return r.json().get("data", [])
                except Exception:
                    pass
            return []

    def query_metrics(self, *a, **k):
        return []

    def query_logs(self, *a, **k):
        return []
