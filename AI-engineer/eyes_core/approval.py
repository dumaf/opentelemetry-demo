"""Centralized human-approval policy for state-changing actions."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone, timedelta
from typing import Any, Callable

from .storage import insert, fetch_one, fetch_all, update, now_iso, new_id

APPROVAL_TTL_SECONDS = 300

READ_ONLY_ACTIONS = {
    "view_dashboard", "view_incident", "view_logs", "view_metrics",
    "view_traces", "view_health", "inspect_fault", "list_faults",
    "run_detection_cycle_read", "generate_summary", "generate_diagnosis",
    "dry_run",
}

STATE_CHANGING_ACTIONS = {
    "trigger_fault", "reset_fault", "reset_all_faults", "run_fault",
    "execute_remediation", "restart_service", "change_config",
    "write_operational_data", "delete_operational_data", "db_mutation",
    "execute_script", "change_detection_settings", "enable_automation",
    "rollback", "recovery",
}

def classify(action: str) -> str:
    if action in READ_ONLY_ACTIONS:
        return "read_only"
    if action in STATE_CHANGING_ACTIONS:
        return "state_changing"
    return "unknown"

def params_hash(params: dict) -> str:
    return hashlib.sha256(json.dumps(params, sort_keys=True, default=str).encode()).hexdigest()

def is_kill_switch_enabled() -> bool:
    r = fetch_one("kill_switch", "id=1")
    if r is None:
        insert("kill_switch", {"id": 1, "enabled": 0, "reason": None, "updated_ts": now_iso()})
        return False
    return bool(r["enabled"])

def set_kill_switch(enabled: bool, reason: str | None = None) -> None:
    r = fetch_one("kill_switch", "id=1")
    if r is None:
        insert("kill_switch", {"id": 1, "enabled": 1 if enabled else 0, "reason": reason, "updated_ts": now_iso()})
    else:
        update("kill_switch", {"enabled": 1 if enabled else 0, "reason": reason, "updated_ts": now_iso()}, "id=1")
    audit("kill_switch", None, "kill_switch", "system", "operator", {"enabled": enabled, "reason": reason}, "success")

def audit(event_type, approval_id, action, target, actor, detail, outcome) -> None:
    insert("audit_log", {
        "id": new_id("aud_"),
        "ts": now_iso(),
        "event_type": event_type,
        "approval_id": approval_id,
        "action": action,
        "target": target,
        "actor": actor,
        "detail": json.dumps(detail, default=str) if detail is not None else None,
        "outcome": outcome,
    })

def propose(action: str, target: str, params: dict, reason: str = "", risk: str = "medium", reversible: bool = True, dry_run_result: Any = None, actor: str = "system") -> dict:
    cls = classify(action)
    if cls == "unknown":
        audit("proposal_rejected", None, action, target, actor, {"reason": "unclassified action"}, "blocked")
        raise ValueError(f"Unknown/unclassified action: {action}")
    if cls == "read_only":
        audit("read_only_executed", None, action, target, actor, {"params": params}, "success")
        return {"action": action, "classification": "read_only", "approved": True, "auto": True}
    # state-changing: create approval
    aid = new_id("apr_")
    ph = params_hash(params)
    expires = (datetime.now(timezone.utc) + timedelta(seconds=APPROVAL_TTL_SECONDS)).isoformat()
    insert("approvals", {
        "id": aid,
        "action": action,
        "target": target,
        "params_json": json.dumps(params, default=str),
        "params_hash": ph,
        "reason": reason,
        "risk": risk,
        "reversible": 1 if reversible else 0,
        "status": "pending",
        "proposed_ts": now_iso(),
        "decided_ts": None,
        "decided_by": None,
        "expires_ts": expires,
        "executed_ts": None,
        "execution_result": None,
        "execution_status": None,
    })
    audit("proposal_created", aid, action, target, actor, {"params": params, "reason": reason, "risk": risk}, "pending")
    return {"approval_id": aid, "action": action, "target": target, "params": params, "status": "pending", "expires_ts": expires}

def get_approval(approval_id: str) -> dict | None:
    r = fetch_one("approvals", "id=?", (approval_id,))
    if r:
        r = dict(r)
        r["params"] = json.loads(r["params_json"])
    return r

def list_pending() -> list[dict]:
    return fetch_all("approvals", where="status='pending'")

def approve(approval_id: str, actor: str = "human") -> dict:
    a = get_approval(approval_id)
    if not a:
        raise ValueError("Approval not found")
    if str(actor).lower().strip() in ("system", "agent", "llm", "ai", "bot", "automated"):
        audit("approval_blocked", approval_id, a["action"], a["target"], actor, {"reason": "agent cannot approve own action"}, "blocked")
        raise ValueError("Agent or system cannot approve actions; explicit human approval required")
    if a["status"] != "pending":
        raise ValueError(f"Approval not pending: {a['status']}")
    # check expiry
    exp = datetime.fromisoformat(a["expires_ts"].replace("Z", "+00:00"))
    if datetime.now(timezone.utc) > exp:
        update("approvals", {"status": "expired"}, "id=?", (approval_id,))
        audit("approval_expired", approval_id, a["action"], a["target"], actor, {}, "expired")
        raise ValueError("Approval expired")
    update("approvals", {"status": "approved", "decided_ts": now_iso(), "decided_by": actor}, "id=?", (approval_id,))
    audit("approval_granted", approval_id, a["action"], a["target"], actor, {}, "approved")
    return get_approval(approval_id)

def reject(approval_id: str, actor: str = "human", reason: str = "") -> dict:
    a = get_approval(approval_id)
    if not a:
        raise ValueError("Approval not found")
    if a["status"] != "pending":
        raise ValueError(f"Approval not pending: {a['status']}")
    update("approvals", {"status": "rejected", "decided_ts": now_iso(), "decided_by": actor}, "id=?", (approval_id,))
    audit("approval_rejected", approval_id, a["action"], a["target"], actor, {"reason": reason}, "rejected")
    return get_approval(approval_id)

def execute(approval_id: str, params: dict, executor: Callable[[], Any], actor: str = "system") -> dict:
    a = get_approval(approval_id)
    if not a:
        raise ValueError("Approval not found")
    if is_kill_switch_enabled():
        audit("execution_blocked", approval_id, a["action"], a["target"], actor, {"reason": "kill switch enabled"}, "blocked")
        raise ValueError("Kill switch is enabled; execution blocked")
    if a["status"] != "approved":
        audit("execution_blocked", approval_id, a["action"], a["target"], actor, {"reason": f"status={a['status']}"}, "blocked")
        raise ValueError(f"Approval not approved: {a['status']}")
    # check expiry
    exp = datetime.fromisoformat(a["expires_ts"].replace("Z", "+00:00"))
    if datetime.now(timezone.utc) > exp:
        update("approvals", {"status": "expired"}, "id=?", (approval_id,))
        audit("execution_blocked", approval_id, a["action"], a["target"], actor, {"reason": "expired"}, "blocked")
        raise ValueError("Approval expired")
    # revalidate params
    if params_hash(params) != a["params_hash"]:
        audit("execution_blocked", approval_id, a["action"], a["target"], actor, {"reason": "params mismatch"}, "blocked")
        raise ValueError("Parameters do not match approved proposal")
    # execute
    update("approvals", {"status": "executing"}, "id=?", (approval_id,))
    try:
        result = executor()
        update("approvals", {"status": "completed", "executed_ts": now_iso(), "execution_result": json.dumps(result, default=str), "execution_status": "success"}, "id=?", (approval_id,))
        audit("execution_completed", approval_id, a["action"], a["target"], actor, {"result": result}, "success")
        return {"approval_id": approval_id, "status": "completed", "result": result}
    except Exception as e:
        update("approvals", {"status": "failed", "executed_ts": now_iso(), "execution_result": str(e), "execution_status": "failed"}, "id=?", (approval_id,))
        audit("execution_failed", approval_id, a["action"], a["target"], actor, {"error": str(e)}, "failed")
        raise
