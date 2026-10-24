"""Incident endpoints."""
from __future__ import annotations

import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fastapi import APIRouter, HTTPException
from eyes_core.storage import fetch_all, fetch_one

router = APIRouter()

@router.get("")
def list_incidents(limit: int = 100):
    rows = fetch_all("incidents", limit=limit)
    return rows

@router.get("/{incident_id}")
def get_incident(incident_id: str):
    r = fetch_one("incidents", "id=?", (incident_id,))
    if not r:
        raise HTTPException(404, "Not found")
    return r

@router.post("/{incident_id}/analyze")
def analyze(incident_id: str):
    from incidents.eyes import run_eyes
    try:
        return run_eyes(incident_id)
    except Exception as e:
        raise HTTPException(500, str(e))

@router.get("/{incident_id}/report")
def report(incident_id: str):
    r = fetch_one("reports", "incident_id=?", (incident_id,))
    if not r:
        raise HTTPException(404, "No report")
    return r

@router.get("/{incident_id}/evidence")
def evidence(incident_id: str):
    r = fetch_one("evidence_bundles", "incident_id=?", (incident_id,))
    if not r:
        raise HTTPException(404, "No evidence")
    import json
    return {"id": r["id"], "window_start": r["window_start"], "window_end": r["window_end"], "payload": json.loads(r["payload_json"])}
