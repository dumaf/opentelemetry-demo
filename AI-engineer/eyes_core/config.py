"""Configuration helpers shared across Eyes components."""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
DB_PATH = DATA_DIR / "eyes.db"
ARTIFACTS_DIR = ROOT / "artifacts"
MODEL_ENV_PATH = ROOT / ".env.model"

DEFAULT_FLAGD_CONFIG_PATH = ROOT.parent / "src" / "flagd" / "demo.flagd.json"
# Allow override via env
FLAGD_CONFIG_PATH = Path(os.environ.get("FLAGD_CONFIG_PATH", str(DEFAULT_FLAGD_CONFIG_PATH)))

import socket
from urllib.parse import urlparse

def _probe(candidate_urls: list[str]) -> str:
    for u in candidate_urls:
        try:
            parsed = urlparse(u)
            host = parsed.hostname or "127.0.0.1"
            port = parsed.port or (443 if parsed.scheme == "https" else 80)
            with socket.create_connection((host, port), timeout=0.2):
                return u
        except Exception:
            continue
    return candidate_urls[0]

FLAGD_UI_BASE = os.environ.get("FLAGD_UI_BASE_URL") or _probe(["http://localhost:4000", "http://localhost:32918"])
PROMETHEUS_BASE = os.environ.get("PROMETHEUS_BASE_URL", "http://localhost:9090")
JAEGER_BASE = os.environ.get("JAEGER_BASE_URL") or _probe(["http://localhost:16686", "http://localhost:32911", "http://localhost:8080/jaeger/ui"])
OPENSEARCH_BASE = os.environ.get("OPENSEARCH_BASE_URL") or _probe(["http://localhost:9200", "http://localhost:32905"])
OTEL_COLLECTOR_HTTP = os.environ.get("OTEL_COLLECTOR_HTTP_URL") or _probe(["http://localhost:4318", "http://localhost:32914"])
GRAFANA_BASE = os.environ.get("GRAFANA_BASE_URL") or _probe(["http://localhost:3000", "http://localhost:32906"])

DETECTION_INTERVAL_SECONDS = int(os.environ.get("DETECTION_INTERVAL_SECONDS", "30"))
DETECTION_COOLDOWN_SECONDS = int(os.environ.get("DETECTION_COOLDOWN_SECONDS", "300"))
EVIDENCE_WINDOW_SECONDS = int(os.environ.get("EVIDENCE_WINDOW_SECONDS", "300"))

def ensure_data_dir() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
