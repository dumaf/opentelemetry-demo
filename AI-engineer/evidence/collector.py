"""Evidence bundle collector."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from eyes_core.storage import insert, now_iso, new_id
from eyes_core.config import EVIDENCE_WINDOW_SECONDS
from telemetry.registry import get

def _parse(ts: str) -> datetime | None:
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except Exception:
        return None

def collect(incident: dict, control_events: list[dict] | None = None) -> dict:
    det_ts = incident["detection_ts"]
    dt = _parse(det_ts) or datetime.now(timezone.utc)
    start = (dt - timedelta(seconds=EVIDENCE_WINDOW_SECONDS)).isoformat()
    end = (dt + timedelta(seconds=60)).isoformat()
    affected = incident.get("affected_services", [])
    svc = affected[0] if affected else None

    evidence_id_map = {}
    bundle = {
        "incident_id": incident["id"],
        "window_start": start,
        "window_end": end,
        "logs": [],
        "metrics": [],
        "traces": [],
        "health": {},
        "control_events": control_events or [],
        "evidence_refs": [],
    }

    # Logs
    osa = get("opensearch")
    if osa and osa.health():
        logs = osa.query_logs(service=svc, start=start, end=end, limit=100)
        for i, r in enumerate(logs, 1):
            eid = f"E{i}"
            evidence_id_map[eid] = ("log", r.payload)
            bundle["logs"].append({"evidence_id": eid, "timestamp": r.timestamp, "service": r.service, "payload": r.payload})
            bundle["evidence_refs"].append(eid)

    # Metrics
    prom = get("prometheus")
    if prom and prom.health():
        offset = len(bundle["evidence_refs"])
        for i, q in enumerate(["up", "http_server_request_duration_seconds_bucket"], 1):
            recs = prom.query_metrics(q, start=start, end=end, step="60s")
            for r in recs[:20]:
                eid = f"E{offset + i}"
                bundle["metrics"].append({"evidence_id": eid, "timestamp": r.timestamp, "service": r.service, "payload": r.payload})
                bundle["evidence_refs"].append(eid)
                offset += 1

    # Traces
    jaeger = get("jaeger")
    if jaeger and jaeger.health():
        offset = len(bundle["evidence_refs"])
        traces = jaeger.query_traces(service=svc, start=start, end=end, limit=20)
        for i, r in enumerate(traces, 1):
            eid = f"E{offset + i}"
            bundle["traces"].append({"evidence_id": eid, "timestamp": r.timestamp, "service": r.service, "payload": r.payload})
            bundle["evidence_refs"].append(eid)

    # Health: prometheus 'up'
    if prom and prom.health():
        try:
            recs = prom.query_metrics("up")
            for r in recs:
                bundle["health"][r.service or "unknown"] = r.payload.get("value")
        except Exception:
            pass

    # Persist
    bid = new_id("eb_")
    insert("evidence_bundles", {
        "id": bid,
        "incident_id": incident["id"],
        "window_start": start,
        "window_end": end,
        "payload_json": json.dumps(bundle, default=str),
        "created_ts": now_iso(),
    })
    # link incident
    from eyes_core.storage import update
    update("incidents", {"evidence_bundle_id": bid}, "id=?", (incident["id"],))
    bundle["bundle_id"] = bid
    return bundle
