"""Brain diagnostic workflow."""
from __future__ import annotations

import json

from eyes_core.storage import fetch_one, insert, update, now_iso, new_id, fetch_all
from evidence.collector import collect
from llm.client import LLMClient
from .prompts import SYSTEM_PROMPT, build_user_prompt
from .validator import validate

def run_brain(incident_id: str, detection_mode: str = "controlled", control_events: list[dict] | None = None) -> dict:
    inc_row = fetch_one("incidents", "id=?", (incident_id,))
    if not inc_row:
        raise ValueError("Incident not found")
    incident = {
        "id": inc_row["id"],
        "detection_ts": inc_row["detection_ts"],
        "affected_services": json.loads(inc_row["affected_services"]),
        "triggering_signals": json.loads(inc_row["triggering_signals"]),
        "severity": inc_row["severity"],
        "rationale": inc_row["rationale"],
        "status": inc_row["status"],
        "detection_method": inc_row.get("detection_method", "automatic"),
    }
    if control_events is None:
        control_events = fetch_all("control_events", limit=50)
    bundle = collect(incident, control_events=control_events)

    client = LLMClient()
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": build_user_prompt(incident, bundle, detection_mode)},
    ]
    result = client.chat(messages)
    parsed = None
    # parse JSON
    content = result["content"].strip()
    if content.startswith("```"):
        content = content.strip("`")
        if content.startswith("json"):
            content = content[4:]
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError:
        start = content.find("{"); end = content.rfind("}")
        if start >= 0 and end > start:
            parsed = json.loads(content[start:end+1])
    if parsed is None:
        parsed = {"error": "no json", "raw": result["content"]}

    parsed.setdefault("incident_id", incident_id)
    parsed.setdefault("detection_mode", detection_mode)
    if isinstance(parsed.get("llm_metadata"), dict):
        parsed["llm_metadata"].setdefault("provider", result["provider"])
        parsed["llm_metadata"].setdefault("model", result["model"])
    else:
        parsed["llm_metadata"] = {"provider": result["provider"], "model": result["model"]}

    ok, errors = validate(parsed, bundle)
    did = new_id("diag_")
    insert("diagnoses", {
        "id": did,
        "incident_id": incident_id,
        "detection_mode": detection_mode,
        "payload_json": json.dumps(parsed, default=str),
        "valid": 1 if ok else 0,
        "validation_errors": json.dumps(errors),
        "created_ts": now_iso(),
    })
    update("incidents", {"status": "diagnosed"}, "id=?", (incident_id,))
    return {"diagnosis_id": did, "incident_id": incident_id, "valid": ok, "errors": errors, "diagnosis": parsed, "bundle_id": bundle["bundle_id"]}
