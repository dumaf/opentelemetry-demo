"""Separate evaluation of a diagnosis against hidden expected outcome."""
from __future__ import annotations

import json

from eyes_core.storage import fetch_one, fetch_all, insert, now_iso, new_id

def evaluate(diagnosis_id: str) -> dict:
    drow = fetch_one("diagnoses", "id=?", (diagnosis_id,))
    if not drow:
        raise ValueError("Diagnosis not found")
    diagnosis = json.loads(drow["payload_json"])
    incident_id = drow["incident_id"]
    inc_row = fetch_one("incidents", "id=?", (incident_id,))
    # hidden expected outcome: from control events in time window around incident
    det_ts = inc_row["detection_ts"] if inc_row else None
    ces = fetch_all("control_events", limit=200)
    # match control events near incident time
    expected_fault = None
    expected_service = None
    if ces:
        # pick most recent control event before detection (trigger/run-start)
        cand = [c for c in ces if c["action"] in ("trigger", "run-start")]
        if cand:
            cand.sort(key=lambda c: c["ts"], reverse=True)
            expected_fault = cand[0]["fault_key"]
            # map fault to service via inventory
            from eyes_core.inventory import build_inventory
            inv = {f["flag_key"]: f for f in build_inventory()}
            if expected_fault in inv:
                expected_service = inv[expected_fault]["affected_service"]

    # diagnosis fields
    affected = diagnosis.get("affected_services", [])
    root_desc = (diagnosis.get("root_cause") or {}).get("description", "")
    conf = (diagnosis.get("confidence") or {}).get("score", 0)

    service_match = expected_service is not None and expected_service in affected
    # root cause inferred correctly: check if expected service/fault keywords appear in root_desc
    fault_keyword = expected_fault.lower() if expected_fault else ""
    root_match = bool(fault_keyword) and fault_keyword.split("failure")[0].strip() in root_desc.lower().replace(" ", "") if fault_keyword else False

    report = {
        "diagnosis_id": diagnosis_id,
        "incident_id": incident_id,
        "expected_fault": expected_fault,
        "expected_service": expected_service,
        "service_identified": service_match,
        "root_cause_likely_correct": root_match,
        "confidence": conf,
        "validation_passed": bool(drow["valid"]),
        "false_positive_risk": "low" if service_match else "high",
        "notes": "Evaluation performed after diagnosis; hidden outcome not provided to model.",
    }
    eid = new_id("eval_")
    insert("evaluations", {
        "id": eid,
        "diagnosis_id": diagnosis_id,
        "incident_id": incident_id,
        "expected_fault": expected_fault,
        "report_json": json.dumps(report, default=str),
        "created_ts": now_iso(),
    })
    return report
