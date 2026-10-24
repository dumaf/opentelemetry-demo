"""Eyes workflow: evidence collection + LLM summary."""
from __future__ import annotations

import json

from eyes_core.storage import fetch_one, update, insert, now_iso, new_id
from evidence.collector import collect
from llm.client import LLMClient, LLMConfig
from llm.prompts import SYSTEM_PROMPT, build_user_prompt
from llm.validation import parse_response, validate_refs

def run_eyes(incident_id: str, control_events: list[dict] | None = None) -> dict:
    inc_row = fetch_one("incidents", "id=?", (incident_id,))
    if not inc_row:
        raise ValueError("Incident not found")
    incident = {
        "id": inc_row["id"],
        "detection_ts": inc_row["detection_ts"],
        "affected_services": __import__("json").loads(inc_row["affected_services"]),
        "triggering_signals": __import__("json").loads(inc_row["triggering_signals"]),
        "severity": inc_row["severity"],
        "rationale": inc_row["rationale"],
        "status": inc_row["status"],
        "detection_method": inc_row.get("detection_method", "automatic"),
    }
    # collect control events separately (not fed as fault identity)
    if control_events is None:
        from eyes_core.storage import fetch_all
        control_events = fetch_all("control_events", limit=50)
    bundle = collect(incident, control_events=control_events)

    # Build diagnostic input excluding hidden fault identity: only bundle evidence
    client = LLMClient()
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": build_user_prompt(incident, bundle)},
    ]
    try:
        result = client.chat(messages)
        content = result["content"]
        parsed = parse_response(content)
        invalid = validate_refs(parsed, bundle)
        if invalid:
            parsed["_invalid_refs"] = invalid
        report_md = f"# Incident Report {incident_id}\n\n" + content
        rid = new_id("rep_")
        insert("reports", {
            "id": rid,
            "incident_id": incident_id,
            "provider": result["provider"],
            "model": result["model"],
            "content_md": report_md,
            "content_json": json.dumps(parsed, default=str),
            "created_ts": now_iso(),
        })
        update("incidents", {"report_id": rid, "status": "investigated"}, "id=?", (incident_id,))
        return {"incident_id": incident_id, "report_id": rid, "bundle_id": bundle["bundle_id"], "parsed": parsed, "raw": content, "invalid_refs": invalid}
    except Exception as e:
        # preserve evidence; store error
        return {"incident_id": incident_id, "error": str(e), "bundle_id": bundle["bundle_id"]}
