"""Report JSON schema validator. Actual organiser schema not supplied; using best-effort schema."""
from __future__ import annotations

REQUIRED = [
    "incident_id", "detection_mode", "summary", "affected_services", "symptoms",
    "root_cause", "causal_analysis", "timeline", "confidence",
    "alternative_hypotheses", "missing_evidence", "recommended_next_steps",
    "telemetry_sources", "llm_metadata",
]

def validate_report(report: dict) -> tuple[bool, list[str]]:
    errors = []
    if not isinstance(report, dict):
        return False, ["report must be object"]
    for k in REQUIRED:
        if k not in report:
            errors.append(f"missing: {k}")
    # confidence
    conf = report.get("confidence")
    if isinstance(conf, dict):
        if not (0 <= conf.get("score", -1) <= 1):
            errors.append("confidence.score out of range")
    # root_cause status
    rc = report.get("root_cause")
    if isinstance(rc, dict) and rc.get("status") not in ("confirmed", "hypothesized", "unresolved"):
        errors.append("invalid root_cause.status")
    return (len(errors) == 0), errors
