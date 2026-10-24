"""Join the existing stage contracts without granting the model an action tool."""

from dataclasses import asdict
from datetime import timedelta
import json
from pathlib import Path
import subprocess
import sys
import uuid

from incident_tools.brain import diagnose, extract, load_run
from incident_tools.brain.claim_validation import validate_claims
from incident_tools.brain.markdown import render_markdown
from incident_tools.brain.report import build_report, to_dict, validate_report
from incident_tools.f02.boundary import iso, timestamp, utc_now
from incident_tools.hands.models import ActionCategory, ActionPlan
from incident_tools.hands.store import HandsStore


def propose_restart(run, facts, diagnosis, validation, report_check, allowed_services, now=None):
    """Return a narrow restart proposal only for a fresh, directly observed stopped component."""
    now = now or utc_now()
    if run.origin != "backend" or run.incident.get("origin") != "backend":
        return None, "Only live backend incidents can produce an action proposal"
    if run.stop_reason != "model_finished" or not run.finished_at:
        return None, "Eyes investigation is incomplete"
    if not 0 <= (now - timestamp(run.finished_at)).total_seconds() <= 300:
        return None, "Eyes evidence is older than five minutes"
    if diagnosis.status != "diagnosed" or diagnosis.confidence != "high":
        return None, "Diagnosis is absent or lacks high categorical confidence"
    if validation.status not in ("validated", "validated_with_warnings") or validation.escalation_recommended or report_check.status != "valid":
        return None, "Diagnosis or report validation requires escalation"
    component = diagnosis.affected_component
    if component not in allowed_services:
        return None, "Affected component is outside the Hands service allowlist"
    if run.incident["service"] not in allowed_services:
        return None, "Incident service is outside the Hands verification allowlist"
    support = set(diagnosis.supporting_fact_ids)
    stopped = [fact for fact in facts if fact.fact_id in support and fact.type == "container_state"
               and fact.service == component and fact.value in ("exited", "dead", "restarting")]
    if not stopped:
        return None, "No cited container observation supports a restart"
    observed = max(stopped, key=lambda fact: timestamp(fact.timestamp))
    if not 0 <= (now - timestamp(observed.timestamp)).total_seconds() <= 300:
        return None, "Container observation is stale"
    later_healthy = [fact for fact in facts if fact.type == "container_state" and fact.service == component
                     and fact.timestamp and timestamp(fact.timestamp) > timestamp(observed.timestamp)
                     and fact.value == "running" and fact.details.get("health") == "healthy"]
    if later_healthy:
        return None, "A later healthy observation contradicts the stopped state"
    alerts = [alert for alert in run.incident["alerts"] if alert.get("metric") in ("error_rate", "latency_p95_ms")
              and isinstance(alert.get("threshold"), (int, float))]
    if not alerts:
        return None, "No supported alert metric is available for recovery verification"
    alert = alerts[0]
    data = {
        "incident_id": run.incident["id"],
        "action_type": ActionCategory.RESTART_SERVICE,
        "target": component,
        "parameters": {},
        "reason": f"Observed {component} container {observed.value}; cited fact {observed.fact_id}. "
                  "A restart is proposed for human review, not a confirmed remedy.",
        "confidence": diagnosis.confidence,
        "risk": "medium",
        "expected_impact": f"Attempt to restore {component}; the affected {run.incident['service']} path must recover under load.",
        "supporting_fact_ids": list(diagnosis.supporting_fact_ids),
        "supporting_evidence_ids": list(diagnosis.supporting_evidence_ids),
        "valid_until": iso(now + timedelta(minutes=5)),
        "verification_criteria": {
            "service": run.incident["service"],
            "metric": alert["metric"],
            "threshold": alert["threshold"],
            "comparison": "<=",
            "min_samples": 2,
            "min_requests": 10,
            "settling_period_seconds": 10,
        },
    }
    return ActionPlan(data, allowed_services=set(allowed_services)), None


def analyze(eyes_record, router, output_dir, hands_dir, allowed_services, now=None):
    """Run Brain on an Eyes record; register only an eligible Hands proposal, never dispatch it."""
    run = load_run(eyes_record)
    facts = extract(run)
    diagnosis = diagnose(run, facts, router)
    validation = validate_claims(diagnosis, facts, run)
    report = build_report(run, facts, diagnosis, validation)
    report_check = validate_report(report, run, facts, diagnosis, validation)
    plan, reason = propose_restart(run, facts, diagnosis, validation, report_check, allowed_services, now)
    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=False)

    def write(name, data):
        (destination / name).write_text(json.dumps(data, indent=2, allow_nan=False) + "\n", encoding="utf-8")

    write("brain_diagnosis.json", asdict(diagnosis))
    write("brain_validation.json", asdict(validation))
    write("brain_report.json", to_dict(report))
    (destination / "brain_report.md").write_text(render_markdown(report), encoding="utf-8")
    handoff = {"incident_id": run.incident["id"], "eyes_origin": run.origin,
               "eyes_stop_reason": run.stop_reason, "brain_status": diagnosis.status,
               "eyes_failure": run.failure,
               "claim_validation": validation.status, "report_validation": report_check.status,
               "hands_status": "escalated", "plan_digest": None, "reason": reason,
               "live_acceptance_complete": False,
               "note": "The organiser JSON schema and a compliant live Action API remain unverified."}
    if plan:
        store = HandsStore(hands_dir)
        try:
            if not store.get_plan(plan.digest):
                store.save_plan(plan.to_dict())
        finally:
            store.close()
        write("hands_plan.json", plan.to_dict())
        handoff.update(hands_status="awaiting_human_approval", plan_digest=plan.digest, reason=None)
    write("pipeline_handoff.json", handoff)
    return handoff


def watch_eyes(eyes_config, eyes_artifact_dir, router, output_root, hands_dir,
               allowed_services, polls=0, launch=subprocess.Popen, incident_id=None):
    """Follow Eyes watch or an explicit queued/incomplete incident investigation."""
    root = Path(output_root)
    root.mkdir(parents=True, exist_ok=True)
    eyes_root = Path(eyes_artifact_dir).resolve()
    command = [sys.executable, "-B", "-m", "incident_tools.eyes", "--config", str(eyes_config)]
    command += ["investigate", "--id", incident_id] if incident_id else ["watch", "--polls", str(polls)]
    process = launch(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                     text=True, bufsize=1)
    failures = 0
    try:
        for line in process.stdout:
            print(line.rstrip("\n"), flush=True)
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(event, dict) or not isinstance(event.get("artifacts"), str):
                continue
            source = (Path(event["artifacts"]) / "checkpoint1_execution_log.json").resolve()
            if not source.is_relative_to(eyes_root) or not source.is_file():
                failures += 1
                print(json.dumps({"pipeline_status": "invalid_eyes_export"}), flush=True)
                continue
            destination = root / ("analysis-" + uuid.uuid4().hex)
            try:
                handoff = analyze(source, router, destination, hands_dir, allowed_services)
                print(json.dumps({"pipeline_status": "analyzed", "output_dir": str(destination),
                                  "handoff": handoff}), flush=True)
            except Exception as exc:
                failures += 1
                print(json.dumps({"pipeline_status": "analysis_failed",
                                  "error_type": type(exc).__name__}), flush=True)
        return process.wait() or (1 if failures else 0)
    finally:
        if process.poll() is None:
            process.terminate()
            process.wait()
