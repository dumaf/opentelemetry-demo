"""FastAPI application entrypoint."""
from __future__ import annotations

import os
import sys
from pathlib import Path

# ensure project root on path
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.app.routers import faults, telemetry, incidents, detection, settings, control_events, brain, approvals

app = FastAPI(title="Eyes API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(faults.router, prefix="/api/faults", tags=["faults"])
app.include_router(telemetry.router, prefix="/api/telemetry", tags=["telemetry"])
app.include_router(incidents.router, prefix="/api/incidents", tags=["incidents"])
app.include_router(detection.router, prefix="/api/detection", tags=["detection"])
app.include_router(settings.router, prefix="/api/settings", tags=["settings"])
app.include_router(control_events.router, prefix="/api/control-events", tags=["control-events"])
app.include_router(brain.router, prefix="/api/brain", tags=["brain"])
app.include_router(approvals.router, prefix="/api/approvals", tags=["approvals"])

@app.get("/api/health")
def health():
    return {"status": "ok"}
