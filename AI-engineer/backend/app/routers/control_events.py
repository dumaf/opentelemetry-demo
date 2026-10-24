"""Control events endpoints."""
from __future__ import annotations

import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fastapi import APIRouter
from eyes_core.storage import fetch_all

router = APIRouter()

@router.get("")
def list_events(limit: int = 100):
    return fetch_all("control_events", limit=limit)
