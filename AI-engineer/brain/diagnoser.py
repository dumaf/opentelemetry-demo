"""Brain diagnostic workflow."""
from __future__ import annotations

import json

from eyes_core.storage import fetch_one, insert, update, now_iso, new_id, fetch_all
from evidence.collector import collect
from llm.client import LLMClient
from .prompts import SYSTEM_PROMPT, build_user_prompt, REQUIRED_KEYS
from .validator import validate


def _normalize_diagnosis(parsed: dict, incident_id: str, detection_mode: str, incident: dict, result: dict) -> dict:
    """Fill in any missing required keys with sensible defaults so partial
    LLM responses still pass structural validation."""
    parsed.setdefault("incident_id", incident_id)
    parsed.setdefault("detection_mode", detection_mode)
    parsed.setdefault("summary", "Diagnosis generated from available telemetry evidence.")
    if not isinstance(parsed.get("affected_services"), list):
        parsed["affected_services"] = incident.get("affected_services", [])
    if not isinstance(parsed.get("symptoms"), list):
        parsed["symptoms"] = []
    rc = parsed.get("root_cause")
    if not isinstance(rc, dict):
        parsed["root_cause"] = {"description": "Undetermined", "status": "unresolved", "evidence_refs": []}
    else:
        rc.setdefault("description", "Undetermined")
        rc.setdefault("evidence_refs", [])
        if rc.get("status") not in ("confirmed", "hypothesized", "unresolved"):
            rc["status"] = "hypothesized"
        if not isinstance(rc.get("evidence_refs"), list):
            rc["evidence_refs"] = []
    if not isinstance(parsed.get("causal_analysis"), list):
        parsed["causal_analysis"] = []
    if not isinstance(parsed.get("timeline"), list):
        parsed["timeline"] = []
    conf = parsed.get("confidence")
    if not isinstance(conf, dict):
        parsed["confidence"] = {"score": 0.3, "rationale": "Low confidence due to incomplete model output."}
    else:
        if not isinstance(conf.get("score"), (int, float)) or isinstance(conf.get("score"), bool):
            conf["score"] = 0.3
        if not isinstance(conf.get("rationale"), str):
            conf["rationale"] = "Confidence rationale not provided by model."
    if not isinstance(parsed.get("alternative_hypotheses"), list):
        parsed["alternative_hypotheses"] = []
    if not isinstance(parsed.get("missing_evidence"), list):
        parsed["missing_evidence"] = []
    if not isinstance(parsed.get("recommended_next_steps"), list):
        parsed["recommended_next_steps"] = []
    if not isinstance(parsed.get("telemetry_sources"), list):
        parsed["telemetry_sources"] = []
    lm = parsed.get("llm_metadata")
    if not isinstance(lm, dict):
        parsed["llm_metadata"] = {"provider": result.get("provider", "unknown"), "model": result.get("model", "unknown")}
    else:
        lm.setdefault("provider", result.get("provider", "unknown"))
        lm.setdefault("model", result.get("model", "unknown"))
    return parsed


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
    bundle = collect(incident)

    client = LLMClient()
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": build_user_prompt(incident, bundle, detection_mode)},
    ]
    result = client.chat(messages)
    parsed = None
    content = result["content"].strip()
    if content.startswith("```"):
        content = content.strip("`")
        if content.startswith("json"):
            content = content[4:]
    try:
        parsed = json.loads(content)
    except (json.JSONDecodeError, ValueError):
        pass
    if parsed is None:
        start = content.find("{"); end = content.rfind("}")
        if start >= 0 and end > start:
            try:
                parsed = json.loads(content[start:end+1])
            except (json.JSONDecodeError, ValueError):
                pass
    if parsed is None:
        repair_msgs = messages + [
            {"role": "assistant", "content": content},
            {"role": "user", "content": "Your previous response was not valid JSON. Return ONLY a valid JSON object matching the schema. No text outside JSON. Include ALL required keys: incident_id, detection_mode, summary, affected_services, symptoms, root_cause, causal_analysis, timeline, confidence, alternative_hypotheses, missing_evidence, recommended_next_steps, telemetry_sources, llm_metadata."},
        ]
        try:
            r2 = client.chat(repair_msgs)
            c2 = r2["content"].strip()
            if c2.startswith("```"):
                c2 = c2.strip("`")
                if c2.startswith("json"):
                    c2 = c2[4:]
            parsed = json.loads(c2)
            result = r2
        except Exception:
            pass
    if parsed is None:
        parsed = {
            "incident_id": incident_id,
            "detection_mode": detection_mode,
            "summary": "Diagnosis could not be parsed from model output.",
            "affected_services": incident.get("affected_services", []),
            "symptoms": [],
            "root_cause": {"description": "Unresolved — model output invalid", "status": "unresolved", "evidence_refs": []},
            "causal_analysis": [],
            "timeline": [],
            "confidence": {"score": 0.0, "rationale": "Model output failed validation; escalated for human review."},
            "alternative_hypotheses": [],
            "missing_evidence": ["Valid structured diagnosis from LLM"],
            "recommended_next_steps": ["Human review required", "Re-run diagnosis with improved prompt"],
            "telemetry_sources": [],
            "llm_metadata": {"provider": result.get("provider",""), "model": result.get("model","")},
            "_raw_response": result.get("content",""),
        }

    parsed = _normalize_diagnosis(parsed, incident_id, detection_mode, incident, result)
    parsed["_raw_response"] = result.get("content", "")
    parsed["raw"] = result.get("content", "")

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
