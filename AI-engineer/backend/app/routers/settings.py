"""Settings endpoints (no secrets exposed)."""
from __future__ import annotations

import sys, os
from pathlib import Path
ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fastapi import APIRouter
from llm.client import LLMConfig
from telemetry.registry import availability

router = APIRouter()

@router.get("/model")
def model_info():
    cfg = LLMConfig()
    return {
        "provider": cfg.provider,
        "model": cfg.model,
        "base_url": cfg.base_url,
        "has_api_key": bool(cfg.api_key),
        "timeout_seconds": cfg.timeout,
    }

@router.get("/telemetry")
def telem():
    return availability()
