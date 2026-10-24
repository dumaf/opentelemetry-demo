"""Blind anomaly detection engine."""
from __future__ import annotations

import time
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from typing import Any

from eyes_core.storage import connect, insert, now_iso, new_id, fetch_all
from eyes_core.config import EVIDENCE_WINDOW_SECONDS
from .rules import Thresholds, error_rate_spike, latency_spike, log_burst
from .grouping import IncidentGrouper

class DetectionEngine:
    def __init__(self, thresholds: Thresholds | None = None):
        self.thresholds = thresholds or Thresholds()
        self.grouper = IncidentGrouper(self.thresholds.cooldown_seconds)
        self._baselines: dict[str, float] = {}

    def _record_cycle(self, signals: list[dict], incidents_created: int):
        insert("detection_cycles", {
            "id": new_id("dc_"),
            "ts": now_iso(),
            "signals_json": __import__("json").dumps(signals),
            "incidents_created": incidents_created,
        })

    def run_cycle(self, telemetry: dict[str, Any]) -> list[dict]:
        """telemetry: dict with keys services, metrics, logs, traces, health (lists of records/summaries)."""
        observations: list[dict] = []
        # Error rate / latency from metrics summaries if provided
        for svc, m in (telemetry.get("service_metrics") or {}).items():
            err = m.get("error_rate", 0.0)
            base_err = self._baselines.get(f"{svc}:err", 0.0)
            if error_rate_spike(err, base_err, self.thresholds):
                observations.append({"service": svc, "signal": "error_rate_spike", "value": err, "baseline": base_err})
            lat = m.get("p99_latency", 0.0)
            base_lat = self._baselines.get(f"{svc}:lat", 0.0)
            if latency_spike(lat, base_lat, self.thresholds):
                observations.append({"service": svc, "signal": "latency_spike", "value": lat, "baseline": base_lat})
            # update baselines (rolling simple avg)
            self._baselines[f"{svc}:err"] = (base_err + err) / 2 if base_err else err
            self._baselines[f"{svc}:lat"] = (base_lat + lat) / 2 if base_lat else lat

        # Log bursts
        log_counts: dict[str, int] = {}
        for log in (telemetry.get("logs") or []):
            if (log.get("severity") or "").upper() in ("ERROR", "FATAL", "CRITICAL"):
                svc = log.get("service") or "unknown"
                log_counts[svc] = log_counts.get(svc, 0) + 1
        for svc, c in log_counts.items():
            if log_burst(c, self.thresholds):
                observations.append({"service": svc, "signal": "log_error_burst", "value": c})

        # Trace failures
        for tr in (telemetry.get("traces") or []):
            if tr.get("has_error"):
                observations.append({"service": tr.get("service") or "unknown", "signal": "trace_failure", "value": tr.get("trace_id")})

        # Health changes
        for svc, h in (telemetry.get("health") or {}).items():
            if h is False or h == "down" or h == "unhealthy":
                observations.append({"service": svc, "signal": "health_degradation", "value": h})

        # Group observations into incidents
        grouped: dict[str, list[dict]] = defaultdict(list)
        for o in observations:
            grouped[o["service"]].append(o)

        incidents_created = 0
        created = []
        for svc, obs in grouped.items():
            signals = sorted({o["signal"] for o in obs})
            key = self.grouper.key_for([svc], signals)
            if not self.grouper.should_create(key):
                continue
            sev = "high" if any(s in ("error_rate_spike", "health_degradation") for s in signals) else "medium"
            inc = {
                "id": new_id("inc_"),
                "detection_ts": now_iso(),
                "affected_services": [svc],
                "triggering_signals": signals,
                "severity": sev,
                "rationale": f"Detected {', '.join(signals)} for {svc} based on telemetry thresholds.",
                "status": "open",
                "detection_method": "automatic",
            }
            insert("incidents", {
                "id": inc["id"],
                "detection_ts": inc["detection_ts"],
                "affected_services": __import__("json").dumps(inc["affected_services"]),
                "triggering_signals": __import__("json").dumps(inc["triggering_signals"]),
                "severity": inc["severity"],
                "rationale": inc["rationale"],
                "status": inc["status"],
                "detection_method": inc["detection_method"],
            })
            created.append(inc)
            incidents_created += 1

        self._record_cycle(observations, incidents_created)
        return created
