"""Validate LLM responses and evidence references."""
from __future__ import annotations

import json

def parse_response(content: str) -> dict:
    content = content.strip()
    if content.startswith("```"):
        content = content.strip("`")
        if content.startswith("json"):
            content = content[4:]
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        # try to find JSON object
        start = content.find("{")
        end = content.rfind("}")
        if start >= 0 and end > start:
            try:
                return json.loads(content[start:end+1])
            except Exception:
                pass
        raise

def validate_refs(resp: dict, bundle: dict) -> list[str]:
    refs = set(bundle.get("evidence_refs", []))
    used = set(resp.get("evidence_refs", []))
    invalid = [r for r in used if r not in refs]
    return invalid
