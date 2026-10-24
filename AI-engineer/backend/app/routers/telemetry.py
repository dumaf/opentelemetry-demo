"""Telemetry endpoints."""
from __future__ import annotations

import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fastapi import APIRouter
from telemetry.registry import availability, get

router = APIRouter()

@router.get("/availability")
def avail():
    return availability()

@router.get("/services/{backend}")
def services(backend: str):
    a = get(backend)
    if not a:
        return {"error": "unknown backend"}
    return {"services": a.list_services(), "health": a.health()}

@router.get("/prometheus/query")
def prom_query(q: str):
    a = get("prometheus")
    if not a or not a.health():
        return {"available": False, "data": []}
    recs = a.query_metrics(q)
    return {"available": True, "data": [r.__dict__ for r in recs]}

@router.get("/logs")
def logs(service: str | None = None, severity: str | None = None, trace_id: str | None = None, limit: int = 100):
    a = get("opensearch")
    if not a or not a.health():
        return {"available": False, "data": []}
    recs = a.query_logs(service=service, severity=severity, trace_id=trace_id, limit=limit)
    return {"available": True, "data": [r.__dict__ for r in recs]}

@router.get("/traces")
def traces(service: str | None = None, limit: int = 50):
    a = get("jaeger")
    if not a or not a.health():
        return {"available": False, "data": []}
    recs = a.query_traces(service=service, limit=limit)
    return {"available": True, "data": [r.__dict__ for r in recs]}
