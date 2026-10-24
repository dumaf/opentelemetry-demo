"""Brain diagnosis endpoints."""
from __future__ import annotations

import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from eyes_core.storage import fetch_all, fetch_one
from brain.diagnoser import run_brain
from brain.evaluator import evaluate
from brain.validator import validate
import json

router = APIRouter()

class DiagnoseReq(BaseModel):
    detection_mode: str = "controlled"

@router.post("/incidents/{incident_id}/diagnose")
def diagnose(incident_id: str, req: DiagnoseReq):
    try:
        return run_brain(incident_id, detection_mode=req.detection_mode)
    except Exception as e:
        raise HTTPException(500, str(e))

@router.get("/diagnoses")
def list_diagnoses(limit: int = 100):
    return fetch_all("diagnoses", limit=limit)

@router.get("/diagnoses/{diagnosis_id}")
def get_diagnosis(diagnosis_id: str):
    r = fetch_one("diagnoses", "id=?", (diagnosis_id,))
    if not r:
        raise HTTPException(404, "Not found")
    r = dict(r)
    r["payload"] = json.loads(r["payload_json"])
    return r

@router.post("/diagnoses/{diagnosis_id}/validate")
def validate_diagnosis(diagnosis_id: str):
    r = fetch_one("diagnoses", "id=?", (diagnosis_id,))
    if not r:
        raise HTTPException(404, "Not found")
    from brain.validator import validate
    from evidence.collector import collect
    # rebuild bundle minimal: use stored; just validate payload against empty refs? Better fetch bundle via incident
    inc = fetch_one("incidents", "id=?", (r["incident_id"],))
    # collect evidence
    bundle = None
    try:
        from incidents.eyes import run_eyes
    except Exception:
        pass
    # Use evidence collector
    incident = {"id": r["incident_id"], "detection_ts": inc["detection_ts"], "affected_services": json.loads(inc["affected_services"]), "triggering_signals": json.loads(inc["triggering_signals"]), "severity": inc["severity"], "rationale": inc["rationale"], "status": inc["status"]}
    from evidence.collector import collect
    bundle = collect(incident)
    diag = json.loads(r["payload_json"])
    ok, errors = validate(diag, bundle)
    return {"valid": ok, "errors": errors}

@router.post("/diagnoses/{diagnosis_id}/evaluate")
def eval_diagnosis(diagnosis_id: str):
    try:
        return evaluate(diagnosis_id)
    except Exception as e:
        raise HTTPException(500, str(e))

@router.get("/diagnoses/{diagnosis_id}/evaluation")
def get_evaluation(diagnosis_id: str):
    rows = fetch_all("evaluations", where="diagnosis_id=?", params=(diagnosis_id,), limit=1)
    return rows[0] if rows else None

@router.get("/model/health")
def model_health():
    from llm.client import LLMClient, LLMConfig
    cfg = LLMConfig()
    return {"has_credentials": bool(cfg.api_key and cfg.model and cfg.base_url), "provider": cfg.provider, "model": cfg.model, "base_url": cfg.base_url}
