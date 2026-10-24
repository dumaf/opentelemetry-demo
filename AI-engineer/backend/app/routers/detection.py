"""Detection control endpoints."""
from __future__ import annotations

import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fastapi import APIRouter
from eyes_core.storage import fetch_all

router = APIRouter()

@router.get("/cycles")
def cycles(limit: int = 50):
    return fetch_all("detection_cycles", limit=limit)

@router.get("/status")
def status():
    return {"engine": "available", "note": "POST /api/detection/run to execute a cycle"}

@router.post("/run")
def run_cycle():
    import sys
    from pathlib import Path
    ROOT = Path(__file__).resolve().parents[3]
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    from telemetry.registry import get
    from detection.engine import DetectionEngine
    from eyes_core.storage import fetch_all
    prom = get("prometheus")
    osa = get("opensearch")
    jaeger = get("jaeger")
    from datetime import datetime, timezone, timedelta
    logs = []
    if osa and osa.health():
        start = (datetime.now(timezone.utc) - timedelta(minutes=15)).isoformat()
        recs = osa.query_logs(start=start, limit=2000)
        logs = [{"service": r.service, "severity": (r.payload or {}).get("severity"), "timestamp": r.timestamp} for r in recs]
    service_metrics = {}
    if prom and prom.health():
        for svc in ["cart", "payment", "checkout", "frontend", "adservice", "emailservice", "recommendationservice", "shippingservice", "productcatalogservice"]:
            service_metrics[svc] = {"error_rate": 0.0, "p99_latency": 0.0}
    health = {}
    if prom and prom.health():
        try:
            for r in prom.query_metrics("up"):
                health[r.service or "unknown"] = r.payload.get("value") == "1"
        except Exception:
            pass
    traces = []
    if jaeger and jaeger.health():
        try:
            start_ts = (datetime.now(timezone.utc) - timedelta(minutes=15)).isoformat()
            for svc_name in list(service_metrics.keys())[:5]:
                trs = jaeger.query_traces(service=svc_name, start=start_ts, limit=10)
                for tr in trs:
                    if tr.payload.get("has_error"):
                        traces.append({"service": svc_name, "has_error": True, "trace_id": tr.payload.get("trace_id")})
        except Exception:
            pass
    telem = {"logs": logs, "service_metrics": service_metrics, "health": health, "traces": traces}
    eng = DetectionEngine()
    created = eng.run_cycle(telem)
    return {"created": len(created), "incidents": created}
