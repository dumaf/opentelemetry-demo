"""Baseline + control-event persistence for FaultCLI."""
from __future__ import annotations

from typing import Any

from eyes_core.storage import (
    connect, fetch_all, fetch_one, insert, update, now_iso, new_id, json_dumps,
)
from eyes_core.config import ensure_data_dir
from eyes_core.inventory import build_inventory

def capture_baselines(source: str = "initial") -> int:
    ensure_data_dir()
    inv = build_inventory()
    n = 0
    for f in inv:
        existing = fetch_one("flag_baselines", "flag_key=?", (f["flag_key"],))
        if existing is None:
            insert("flag_baselines", {
                "flag_key": f["flag_key"],
                "default_variant": str(f["configured_default"]),
                "captured_ts": now_iso(),
                "source": source,
            })
            n += 1
    return n

def get_baseline(key: str) -> str | None:
    r = fetch_one("flag_baselines", "flag_key=?", (key,))
    return r["default_variant"] if r else None

def record_control_event(fault_key, action, variant_from, variant_to, success, error=None, duration_s=None, actor="faultcli") -> str:
    eid = new_id("ce_")
    insert("control_events", {
        "id": eid,
        "ts": now_iso(),
        "actor": actor,
        "fault_key": fault_key,
        "action": action,
        "variant_from": variant_from,
        "variant_to": variant_to,
        "success": 1 if success else 0,
        "error": error,
        "duration_s": duration_s,
        "is_tool_generated": 1,
    })
    return eid

def list_control_events(limit: int = 100) -> list[dict[str, Any]]:
    return fetch_all("control_events", limit=limit)
