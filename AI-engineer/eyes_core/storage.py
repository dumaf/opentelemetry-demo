"""SQLite storage helpers shared by Eyes components."""
from __future__ import annotations

import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from .config import DB_PATH, ensure_data_dir

SCHEMA = """
CREATE TABLE IF NOT EXISTS incidents (
    id TEXT PRIMARY KEY,
    detection_ts TEXT NOT NULL,
    affected_services TEXT NOT NULL,
    triggering_signals TEXT NOT NULL,
    severity TEXT NOT NULL,
    rationale TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'open',
    evidence_bundle_id TEXT,
    report_id TEXT,
    detection_method TEXT DEFAULT 'automatic'
);
CREATE TABLE IF NOT EXISTS evidence_bundles (
    id TEXT PRIMARY KEY,
    incident_id TEXT NOT NULL,
    window_start TEXT NOT NULL,
    window_end TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_ts TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS control_events (
    id TEXT PRIMARY KEY,
    ts TEXT NOT NULL,
    actor TEXT NOT NULL,
    fault_key TEXT NOT NULL,
    action TEXT NOT NULL,
    variant_from TEXT,
    variant_to TEXT,
    success INTEGER NOT NULL,
    error TEXT,
    duration_s REAL,
    is_tool_generated INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS flag_baselines (
    flag_key TEXT PRIMARY KEY,
    default_variant TEXT NOT NULL,
    captured_ts TEXT NOT NULL,
    source TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS detection_cycles (
    id TEXT PRIMARY KEY,
    ts TEXT NOT NULL,
    signals_json TEXT NOT NULL,
    incidents_created INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS reports (
    id TEXT PRIMARY KEY,
    incident_id TEXT NOT NULL,
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    content_md TEXT NOT NULL,
    content_json TEXT NOT NULL,
    created_ts TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS diagnoses (
    id TEXT PRIMARY KEY,
    incident_id TEXT NOT NULL,
    detection_mode TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    valid INTEGER NOT NULL DEFAULT 0,
    validation_errors TEXT,
    created_ts TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS evaluations (
    id TEXT PRIMARY KEY,
    diagnosis_id TEXT NOT NULL,
    incident_id TEXT NOT NULL,
    expected_fault TEXT,
    report_json TEXT NOT NULL,
    created_ts TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS approvals (
    id TEXT PRIMARY KEY,
    action TEXT NOT NULL,
    target TEXT NOT NULL,
    params_json TEXT NOT NULL,
    params_hash TEXT NOT NULL,
    reason TEXT,
    risk TEXT,
    reversible INTEGER NOT NULL DEFAULT 1,
    status TEXT NOT NULL DEFAULT 'pending',
    proposed_ts TEXT NOT NULL,
    decided_ts TEXT,
    decided_by TEXT,
    expires_ts TEXT NOT NULL,
    executed_ts TEXT,
    execution_result TEXT,
    execution_status TEXT
);
CREATE TABLE IF NOT EXISTS audit_log (
    id TEXT PRIMARY KEY,
    ts TEXT NOT NULL,
    event_type TEXT NOT NULL,
    approval_id TEXT,
    action TEXT,
    target TEXT,
    actor TEXT,
    detail TEXT,
    outcome TEXT
);
CREATE TABLE IF NOT EXISTS kill_switch (
    id INTEGER PRIMARY KEY CHECK (id=1),
    enabled INTEGER NOT NULL DEFAULT 0,
    reason TEXT,
    updated_ts TEXT NOT NULL
);
"""

def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

def new_id(prefix: str = "") -> str:
    return f"{prefix}{uuid.uuid4().hex[:12]}"

@contextmanager
def connect(db_path: Path | None = None):
    ensure_data_dir()
    path = db_path or DB_PATH
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    try:
        conn.executescript(SCHEMA)
        yield conn
        conn.commit()
    finally:
        conn.close()

def insert(table: str, row: dict[str, Any]) -> None:
    with connect() as conn:
        cols = ", ".join(row.keys())
        placeholders = ", ".join("?" for _ in row)
        conn.execute(f"INSERT INTO {table} ({cols}) VALUES ({placeholders})", list(row.values()))

def fetch_all(table: str, where: str = "", params: Iterable[Any] = (), limit: int = 500) -> list[dict[str, Any]]:
    with connect() as conn:
        q = f"SELECT * FROM {table}"
        if where:
            q += f" WHERE {where}"
        q += f" ORDER BY rowid DESC LIMIT {limit}"
        cur = conn.execute(q, list(params))
        return [dict(r) for r in cur.fetchall()]

def fetch_one(table: str, where: str, params: Iterable[Any] = ()) -> dict[str, Any] | None:
    with connect() as conn:
        cur = conn.execute(f"SELECT * FROM {table} WHERE {where} LIMIT 1", list(params))
        r = cur.fetchone()
        return dict(r) if r else None

def update(table: str, sets: dict[str, Any], where: str, params: Iterable[Any] = ()) -> None:
    with connect() as conn:
        set_clause = ", ".join(f"{k}=?" for k in sets)
        conn.execute(f"UPDATE {table} SET {set_clause} WHERE {where}", list(sets.values()) + list(params))

def json_dumps(obj: Any) -> str:
    return json.dumps(obj, default=str)
