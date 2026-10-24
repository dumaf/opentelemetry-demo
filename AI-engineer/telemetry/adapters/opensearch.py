"""OpenSearch adapter for logs."""
from __future__ import annotations

import httpx

from eyes_core.config import OPENSEARCH_BASE
from .base import TelemetryRecord

class OpenSearchAdapter:
    name = "opensearch"
    INDEX = "otel-logs*"

    def __init__(self, base_url: str | None = None, timeout: float = 10.0):
        self.base = (base_url or OPENSEARCH_BASE).rstrip("/")
        self.timeout = timeout

    def _c(self):
        return httpx.Client(base_url=self.base, timeout=self.timeout)

    def health(self) -> bool:
        try:
            with self._c() as c:
                r = c.get("/")
                return r.status_code < 400
        except Exception:
            return False

    def list_services(self) -> list[str]:
        return []

    def query_logs(self, service=None, severity=None, trace_id=None, start=None, end=None, limit=100, **kw):
        must = []
        if service:
            must.append({"match": {"resource.service.name": service}})
        if severity:
            must.append({"match": {"severity.text": severity}})
        if trace_id:
            must.append({"term": {"trace_id": trace_id}})
        if start or end:
            rng = {}
            if start:
                rng["gte"] = start
            if end:
                rng["lte"] = end
            must.append({"range": {"@timestamp": rng}})
        body = {"size": limit, "query": {"bool": {"must": must}} if must else {"match_all": {}}, "sort": [{"@timestamp": "desc"}]}
        try:
            with self._c() as c:
                r = c.post(f"/{self.INDEX}/_search", json=body)
                r.raise_for_status()
                hits = r.json().get("hits", {}).get("hits", [])
        except Exception:
            return []
        out = []
        for h in hits:
            src = h.get("_source", {})
            out.append(TelemetryRecord(
                source="opensearch", kind="log",
                timestamp=src.get("@timestamp", ""),
                service=src.get("resource", {}).get("service.name") or src.get("service", {}).get("name"),
                payload={"message": src.get("body", src.get("message")), "severity": src.get("severity", {}).get("text"), "trace_id": src.get("trace_id"), "span_id": src.get("span_id")},
                raw=src,
            ))
        return out

    def query_metrics(self, *a, **k):
        return []

    def query_traces(self, *a, **k):
        return []
