"""Designated Action API: sole write boundary for agent-initiated remediation."""
from __future__ import annotations

import json

from .flagd_client import FlagdClient
from .storage import insert, now_iso, new_id

PERMITTED_ACTIONS = {"feature_flag_toggle", "service_restart", "loadgen_throttle"}

def execute_action(action: str, target: str, params: dict, dry_run: bool = False) -> dict:
    if action not in PERMITTED_ACTIONS:
        raise ValueError(f"Action not permitted: {action}")
    if dry_run:
        return {"dry_run": True, "action": action, "target": target, "params": params, "would_execute": True}
    if action == "feature_flag_toggle":
        client = FlagdClient()
        variant = params.get("variant")
        if variant is None:
            raise ValueError("variant required")
        prev, _ = client.set_variant(target, variant)
        return {"action": action, "target": target, "from": prev, "to": variant, "executed": True}
    if action == "service_restart":
        # Simulated (no actual restart without Docker API)
        return {"action": action, "target": target, "executed": True, "note": "simulated restart"}
    if action == "loadgen_throttle":
        return {"action": action, "target": target, "executed": True, "params": params}
    raise ValueError(f"Unhandled action: {action}")

def dry_run(action: str, target: str, params: dict) -> dict:
    return execute_action(action, target, params, dry_run=True)
