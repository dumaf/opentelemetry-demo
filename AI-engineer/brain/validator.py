"""Validate Brain diagnosis JSON."""
from __future__ import annotations

import json
import re
from datetime import datetime

from .prompts import REQUIRED_KEYS

VALID_STATUSES = {"confirmed", "hypothesized", "unresolved"}

def _is_iso(ts):
    try:
        datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
        return True
    except Exception:
        return False

def validate(diagnosis: dict, bundle: dict) -> tuple[bool, list[str]]:
    errors = []
    if not isinstance(diagnosis, dict):
        return False, ["diagnosis must be an object"]
    for k in REQUIRED_KEYS:
        if k not in diagnosis:
            errors.append(f"missing key: {k}")
    # types
    if not isinstance(diagnosis.get("affected_services"), list):
        errors.append("affected_services must be list")
    if not isinstance(diagnosis.get("symptoms"), list):
        errors.append("symptoms must be list")
    if not isinstance(diagnosis.get("causal_analysis"), list):
        errors.append("causal_analysis must be list")
    if not isinstance(diagnosis.get("timeline"), list):
        errors.append("timeline must be list")
    if not isinstance(diagnosis.get("alternative_hypotheses"), list):
        errors.append("alternative_hypotheses must be list")
    if not isinstance(diagnosis.get("missing_evidence"), list):
        errors.append("missing_evidence must be list")
    if not isinstance(diagnosis.get("recommended_next_steps"), list):
        errors.append("recommended_next_steps must be list")
    if not isinstance(diagnosis.get("telemetry_sources"), list):
        errors.append("telemetry_sources must be list")

    rc = diagnosis.get("root_cause")
    if not isinstance(rc, dict):
        errors.append("root_cause must be object")
    else:
        if rc.get("status") not in VALID_STATUSES:
            errors.append(f"invalid root_cause.status: {rc.get('status')}")
        if not isinstance(rc.get("evidence_refs"), list):
            errors.append("root_cause.evidence_refs must be list")

    conf = diagnosis.get("confidence")
    if not isinstance(conf, dict):
        errors.append("confidence must be object")
    else:
        score = conf.get("score")
        if not isinstance(score, (int, float)) or isinstance(score, bool):
            errors.append("confidence.score must be number")
        elif score < 0.0 or score > 1.0:
            errors.append("confidence.score out of range 0-1")
        if not isinstance(conf.get("rationale"), str):
            errors.append("confidence.rationale must be string")

    for t in diagnosis.get("timeline", []):
        if isinstance(t, dict) and "timestamp" in t:
            if not _is_iso(t["timestamp"]):
                errors.append(f"bad timestamp: {t['timestamp']}")

    # evidence refs existence
    valid_refs = set(bundle.get("evidence_refs", []))
    def check_refs(refs, where):
        for r in refs or []:
            if r not in valid_refs:
                errors.append(f"unknown evidence ref {r} in {where}")
    for s in diagnosis.get("symptoms", []):
        if isinstance(s, dict):
            check_refs(s.get("evidence_refs", []), "symptoms")
    if isinstance(rc, dict):
        check_refs(rc.get("evidence_refs", []), "root_cause")
    for c in diagnosis.get("causal_analysis", []):
        if isinstance(c, dict):
            check_refs(c.get("evidence_refs", []), "causal_analysis")
    for a in diagnosis.get("alternative_hypotheses", []):
        if isinstance(a, dict):
            check_refs(a.get("supporting_evidence", []), "alt.supporting")
            check_refs(a.get("contradicting_evidence", []), "alt.contradicting")

    lm = diagnosis.get("llm_metadata")
    if not isinstance(lm, dict):
        errors.append("llm_metadata must be object")
    else:
        if not lm.get("provider"):
            errors.append("llm_metadata.provider missing")
        if not lm.get("model"):
            errors.append("llm_metadata.model missing")

    return (len(errors) == 0), errors
