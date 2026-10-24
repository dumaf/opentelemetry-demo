"""Fault management endpoints."""
from __future__ import annotations

import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from eyes_core.inventory import build_inventory
from eyes_core.flagd_client import FlagdClient
from faultcli.state import capture_baselines, get_baseline, record_control_event, list_control_events

router = APIRouter()

class TriggerReq(BaseModel):
    variant: str

@router.get("")
def list_faults():
    return build_inventory()

@router.get("/{fault}")
def inspect_fault(fault: str):
    inv = {f["flag_key"]: f for f in build_inventory()}
    if fault not in inv:
        raise HTTPException(404, "Unknown fault")
    return inv[fault]

@router.get("/status/all")
def status():
    capture_baselines()
    client = FlagdClient()
    try:
        flags = client.get_flags()
    except Exception as e:
        return {"error": str(e), "state": "unknown"}
    out = []
    for key, f in flags.items():
        cur = f.get("defaultVariant")
        base = get_baseline(key)
        state = "active" if (base is not None and str(cur) != str(base)) else "inactive"
        if base is None:
            state = "unknown-baseline"
        out.append({"flag": key, "current": cur, "baseline": base, "state": state})
    return out

@router.post("/{fault}/trigger")
def trigger(fault: str, req: TriggerReq):
    inv = {f["flag_key"]: f for f in build_inventory()}
    if fault not in inv:
        raise HTTPException(404, "Unknown fault")
    if req.variant not in inv[fault]["available_variants"]:
        raise HTTPException(400, "Invalid variant")
    capture_baselines()
    # Require human approval before execution
    from eyes_core.approval import propose
    proposal = propose(
        action="trigger_fault",
        target=fault,
        params={"variant": req.variant},
        reason=f"Trigger {fault} to {req.variant}",
        risk="high",
        reversible=True,
    )
    return {"approval_required": True, "approval": proposal}

@router.post("/{fault}/reset")
def reset(fault: str):
    capture_baselines()
    base = get_baseline(fault)
    try:
        cur = FlagdClient().get_flag(fault).get("defaultVariant")
    except Exception as e:
        raise HTTPException(500, str(e))
    from eyes_core.approval import propose
    proposal = propose(
        action="reset_fault",
        target=fault,
        params={"from": cur, "to": base},
        reason=f"Reset {fault} from {cur} to {base}",
        risk="medium",
        reversible=True,
    )
    return {"approval_required": True, "approval": proposal}

@router.post("/reset-all")
def reset_all():
    capture_baselines()
    client = FlagdClient()
    try:
        flags = client.get_flags()
    except Exception as e:
        raise HTTPException(500, str(e))
    n = 0
    for key in flags:
        base = get_baseline(key)
        if base is None:
            continue
        cur = flags[key].get("defaultVariant")
        if str(cur) == str(base):
            continue
        try:
            client.reset_flag(key, base)
            record_control_event(key, "reset", cur, base, True)
            n += 1
        except Exception as e:
            record_control_event(key, "reset", cur, base, False, error=str(e))
    return {"reset": n}

@router.post("/{fault}/run")
def run_fault(fault: str, duration: int = 30, variant: str | None = None):
    import time
    inv = {f["flag_key"]: f for f in build_inventory()}
    if fault not in inv:
        raise HTTPException(404, "Unknown fault")
    if variant is None:
        vs = [v for v in inv[fault]["available_variants"] if v != "off"]
        variant = vs[0] if vs else None
    if variant not in inv[fault]["available_variants"]:
        raise HTTPException(400, "Invalid variant")
    capture_baselines()
    base = get_baseline(fault)
    client = FlagdClient()
    try:
        prev, _ = client.set_variant(fault, variant)
        record_control_event(fault, "run-start", prev, variant, True)
    except Exception as e:
        record_control_event(fault, "run-start", None, variant, False, error=str(e))
        raise HTTPException(500, str(e))
    time.sleep(duration)
    try:
        client.reset_flag(fault, base if base is not None else "off")
        record_control_event(fault, "run-end", variant, base, True)
    except Exception as e:
        record_control_event(fault, "run-end", variant, base, False, error=str(e))
    return {"flag": fault, "variant": variant, "duration": duration, "restored": True}

@router.get("/history/list")
def history(limit: int = 50):
    return list_control_events(limit=limit)
