"""Approval workflow endpoints."""
from __future__ import annotations

import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from eyes_core.approval import (propose, approve, reject, execute, get_approval,
    list_pending, is_kill_switch_enabled, set_kill_switch, audit, classify)
from eyes_core.storage import fetch_all

router = APIRouter()

class ProposeReq(BaseModel):
    action: str
    target: str
    params: dict = {}
    reason: str = ""
    risk: str = "medium"
    reversible: bool = True

class DecideReq(BaseModel):
    actor: str = "human"
    reason: str = ""

@router.post("/propose")
def propose_action(req: ProposeReq):
    try:
        return propose(req.action, req.target, req.params, req.reason, req.risk, req.reversible)
    except ValueError as e:
        raise HTTPException(400, str(e))

@router.get("")
def list_approvals():
    return list_pending()

@router.get("/all")
def list_all():
    return fetch_all("approvals", limit=200)

@router.get("/audit")
def list_audit(limit: int = 100):
    rows = fetch_all("audit_log", limit=limit)
    out = []
    for r in rows:
        row_dict = dict(r)
        if row_dict.get("detail"):
            try:
                row_dict["detail"] = json.loads(row_dict["detail"])
            except Exception:
                pass
        out.append(row_dict)
    return out

@router.get("/{aid}")
def get(aid: str):
    a = get_approval(aid)
    if not a:
        raise HTTPException(404, "Not found")
    return a

@router.post("/{aid}/approve")
def approve_action(aid: str, req: DecideReq):
    try:
        return approve(aid, req.actor)
    except ValueError as e:
        raise HTTPException(400, str(e))

@router.post("/{aid}/reject")
def reject_action(aid: str, req: DecideReq):
    try:
        return reject(aid, req.actor, req.reason)
    except ValueError as e:
        raise HTTPException(400, str(e))

@router.post("/{aid}/execute")
def execute_action(aid: str, req: DecideReq):
    from eyes_core.approval import get_approval, execute
    a = get_approval(aid)
    if not a:
        raise HTTPException(404, "Not found")
    action = a["action"]
    target = a["target"]
    params = a["params"]
    # Build executor based on action type
    def executor():
        if action == "trigger_fault":
            from eyes_core.action_api import execute_action
            from faultcli.state import record_control_event, capture_baselines
            capture_baselines()
            res = execute_action("feature_flag_toggle", target, {"variant": params["variant"]})
            record_control_event(target, "trigger", res.get("from"), params["variant"], True)
            return res
        elif action == "reset_fault":
            from eyes_core.action_api import execute_action
            from faultcli.state import record_control_event, get_baseline
            res = execute_action("feature_flag_toggle", target, {"variant": params["to"]})
            record_control_event(target, "reset", params.get("from"), params["to"], True)
            base = get_baseline(target)
            recovered = (str(params.get("to")) == str(base)) or (str(res.get("to")) == str(base))
            res["recovery_verification"] = {
                "recovered": recovered,
                "target": target,
                "verified_variant": res.get("to"),
                "baseline": base,
                "status": "verified" if recovered else "unverified"
            }
            return res
        elif action == "reset_all_faults":
            from faultcli.state import capture_baselines, get_baseline, record_control_event
            from eyes_core.flagd_client import FlagdClient
            client = FlagdClient()
            flags = client.get_flags()
            n = 0
            for key in flags:
                base = get_baseline(key)
                if base is None:
                    continue
                cur = flags[key].get("defaultVariant")
                if str(cur) == str(base):
                    continue
                client.reset_flag(key, base)
                record_control_event(key, "reset", cur, base, True)
                n += 1
            return {
                "action": "reset_all_faults",
                "reset_count": n,
                "recovery_verification": {"recovered": True, "status": "verified", "reset_count": n}
            }
        elif action == "execute_remediation":
            from eyes_core.action_api import execute_action
            from faultcli.state import get_baseline
            op = params.get("operation", "feature_flag_toggle")
            res = execute_action(op, target, params)
            base = get_baseline(target)
            recovered = True
            if base is not None and "variant" in params:
                recovered = str(params["variant"]) == str(base)
            res["recovery_verification"] = {
                "recovered": recovered,
                "target": target,
                "status": "verified" if recovered else "partial"
            }
            return res
        else:
            raise ValueError(f"Unknown action: {action}")
    try:
        return execute(aid, params, executor, req.actor)
    except ValueError as e:
        raise HTTPException(400, str(e))

@router.get("/kill-switch/status")
def ks_status():
    return {"enabled": is_kill_switch_enabled()}

@router.post("/kill-switch/enable")
def ks_enable(req: DecideReq):
    set_kill_switch(True, req.reason)
    return {"enabled": True}

@router.post("/kill-switch/disable")
def ks_disable(req: DecideReq):
    set_kill_switch(False, req.reason)
    return {"enabled": False}

@router.get("/audit")
def audit_log(limit: int = 100):
    return fetch_all("audit_log", limit=limit)

@router.get("/classify/{action}")
def classify_action(action: str):
    return {"action": action, "classification": classify(action)}
