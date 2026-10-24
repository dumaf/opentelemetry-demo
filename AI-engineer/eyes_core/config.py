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

FLAGD_UI_BASE = os.environ.get("FLAGD_UI_BASE_URL", "http://localhost:4000")
PROMETHEUS_BASE = os.environ.get("PROMETHEUS_BASE_URL", "http://localhost:9090")
JAEGER_BASE = os.environ.get("JAEGER_BASE_URL", "http://localhost:16686")
OPENSEARCH_BASE = os.environ.get("OPENSEARCH_BASE_URL", "http://localhost:9200")
OTEL_COLLECTOR_HTTP = os.environ.get("OTEL_COLLECTOR_HTTP_URL", "http://localhost:4318")
GRAFANA_BASE = os.environ.get("GRAFANA_BASE_URL", "http://localhost:3000")

DETECTION_INTERVAL_SECONDS = int(os.environ.get("DETECTION_INTERVAL_SECONDS", "30"))
DETECTION_COOLDOWN_SECONDS = int(os.environ.get("DETECTION_COOLDOWN_SECONDS", "300"))
EVIDENCE_WINDOW_SECONDS = int(os.environ.get("EVIDENCE_WINDOW_SECONDS", "300"))

def ensure_data_dir() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
