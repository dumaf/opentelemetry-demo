"""Fault inventory derived from src/flagd/demo.flagd.json."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .config import FLAGD_CONFIG_PATH, ARTIFACTS_DIR

SERVICE_MAP = {
    "ad": "ad",
    "cart": "cart",
    "payment": "payment",
    "email": "email",
    "productCatalog": "product-catalog",
    "recommendation": "recommendation",
    "shipping": "shipping",
    "checkout": "checkout",
    "frontend": "frontend",
    "kafka": "kafka/fraud-detection",
    "ai": "agent/llm",
    "image": "image-provider",
    "loadGenerator": "load-generator",
}

def infer_service(key: str) -> str:
    for prefix, svc in SERVICE_MAP.items():
        if key.lower().startswith(prefix.lower()):
            return svc
    # special cases
    if "MetricCardinality" in key:
        return "cart"
    if "failedReadiness" in key:
        return "cart"
    if "intlShipping" in key:
        return "shipping"
    return "unknown"

def build_inventory(config_path: Path | None = None) -> list[dict[str, Any]]:
    path = config_path or FLAGD_CONFIG_PATH
    raw = json.loads(path.read_text())
    flags = raw.get("flags", {})
    out = []
    for key, defn in flags.items():
        variants = defn.get("variants", {})
        default = defn.get("defaultVariant")
        targeting = defn.get("targeting")
        schedulable = defn.get("metadata", {}).get("schedulable", True)
        svc = infer_service(key)
        out.append({
            "flag_key": key,
            "description": defn.get("description", ""),
            "available_variants": list(variants.keys()),
            "variant_values": variants,
            "configured_default": default,
            "state": defn.get("state", "UNKNOWN"),
            "targeting": targeting,
            "schedulable": schedulable,
            "affected_service": svc,
            "expected_symptoms": expected_symptoms(key, defn.get("description", ""), svc),
            "source_config_reference": f"{path}:{key}",
        })
    return out

def expected_symptoms(key: str, desc: str, svc: str) -> list[str]:
    d = desc.lower()
    syms = []
    if "fail" in d:
        syms.append("increased error rate / failed requests")
    if "slow" in d or "delay" in d:
        syms.append("latency spike")
    if "memory leak" in d or "memory pressure" in d:
        syms.append("memory growth / OOM risk")
    if "cpu" in d:
        syms.append("elevated CPU")
    if "kafka" in d or "consumer" in d or "lag" in d:
        syms.append("consumer lag increase")
    if "readiness" in d:
        syms.append("readiness probe failures")
    if "cardinality" in d:
        syms.append("metric cardinality overflow")
    if "flood" in d:
        syms.append("traffic spike")
    if not syms:
        syms.append("behavior change per flag description")
    syms.append(f"affected service: {svc}")
    return syms

def save_inventory(config_path: Path | None = None) -> Path:
    inv = build_inventory(config_path)
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    out = ARTIFACTS_DIR / "fault_inventory.json"
    out.write_text(json.dumps(inv, indent=2))
    return out
