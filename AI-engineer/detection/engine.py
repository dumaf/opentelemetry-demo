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

    def _query_prometheus_error_rates(self, telemetry: dict) -> list[dict]:
        """Query Prometheus for actual HTTP error rates per service."""
        observations = []
        try:
            from telemetry.registry import get
            prom = get("prometheus")
            if not prom or not prom.health():
                return observations
            error_recs = prom.query_instant(
                'sum by (service_name) (rate(http_server_request_duration_seconds_count{http_response_status_code=~"5.."}[5m]))'
            )
            total_recs = prom.query_instant(
                'sum by (service_name) (rate(http_server_request_duration_seconds_count[5m]))'
            )
            totals = {}
            for r in total_recs:
                svc = r.service or "unknown"
                val = float(r.payload.get("value", 0))
                if val > 0:
                    totals[svc] = val
            for r in error_recs:
                svc = r.service or "unknown"
                err_val = float(r.payload.get("value", 0))
                total_val = totals.get(svc, 1.0)
                err_rate = err_val / total_val if total_val > 0 else 0
                if err_rate >= self.thresholds.error_rate_abs:
                    observations.append({"service": svc, "signal": "error_rate_spike", "value": err_rate, "baseline": 0.0})
        except Exception:
            pass
        return observations

    def _query_prometheus_latency(self, telemetry: dict) -> list[dict]:
        """Query Prometheus for p99 latency anomalies per service."""
        observations = []
        try:
            from telemetry.registry import get
            prom = get("prometheus")
            if not prom or not prom.health():
                return observations
            recs = prom.query_instant(
                'histogram_quantile(0.99, sum by (service_name, le) (rate(http_server_request_duration_seconds_bucket[5m])))'
            )
            for r in recs:
                svc = r.service or "unknown"
                val = float(r.payload.get("value", 0))
                baseline = self._baselines.get(f"{svc}:lat", 0.0)
                if val > 2.0 or (baseline > 0 and val >= baseline * self.thresholds.latency_factor):
                    observations.append({"service": svc, "signal": "latency_spike", "value": val, "baseline": baseline})
                if val > 0:
                    self._baselines[f"{svc}:lat"] = (baseline + val) / 2 if baseline else val
        except Exception:
            pass
        return observations

    def run_cycle(self, telemetry: dict[str, Any]) -> list[dict]:
        """telemetry: dict with keys services, metrics, logs, traces, health (lists of records/summaries)."""
        observations: list[dict] = []
        for svc, m in (telemetry.get("service_metrics") or {}).items():
            err = m.get("error_rate", 0.0)
            base_err = self._baselines.get(f"{svc}:err", 0.0)
            if error_rate_spike(err, base_err, self.thresholds):
                observations.append({"service": svc, "signal": "error_rate_spike", "value": err, "baseline": base_err})
            lat = m.get("p99_latency", 0.0)
            base_lat = self._baselines.get(f"{svc}:lat", 0.0)
            if latency_spike(lat, base_lat, self.thresholds):
                observations.append({"service": svc, "signal": "latency_spike", "value": lat, "baseline": base_lat})
            self._baselines[f"{svc}:err"] = (base_err + err) / 2 if base_err else err
            self._baselines[f"{svc}:lat"] = (base_lat + lat) / 2 if base_lat else lat

        # Live Prometheus queries for error rates and latency
        observations.extend(self._query_prometheus_error_rates(telemetry))
        observations.extend(self._query_prometheus_latency(telemetry))

        # Log bursts
        log_counts: dict[str, int] = {}
        for log in (telemetry.get("logs") or []):
            if (log.get("severity") or "").upper() in ("ERROR", "FATAL", "CRITICAL"):
                svc = log.get("service") or "unknown"
                log_counts[svc] = log_counts.get(svc, 0) + 1
        for svc, c in log_counts.items():
            if log_burst(c, self.thresholds):
                observations.append({"service": svc, "signal": "log_error_burst", "value": c})

        # Also detect WARNING log surges (many faults emit WARNINGs, not ERRORs)
        warn_counts: dict[str, int] = {}
        for log in (telemetry.get("logs") or []):
            if (log.get("severity") or "").upper() in ("WARN", "WARNING"):
                svc = log.get("service") or "unknown"
                warn_counts[svc] = warn_counts.get(svc, 0) + 1
        for svc, c in warn_counts.items():
            if c >= 5:
                observations.append({"service": svc, "signal": "warning_log_surge", "value": c})

        # Trace failures
        for tr in (telemetry.get("traces") or []):
            if tr.get("has_error"):
                observations.append({"service": tr.get("service") or "unknown", "signal": "trace_failure", "value": tr.get("trace_id")})

        # Health changes
        for svc, h in (telemetry.get("health") or {}).items():
            if h is False or h == "down" or h == "unhealthy":
                observations.append({"service": svc, "signal": "health_degradation", "value": h})

        # Check for services with up=0 from Prometheus
        try:
            from telemetry.registry import get
            prom = get("prometheus")
            if prom and prom.health():
                up_recs = prom.query_instant("up")
                for r in up_recs:
                    svc = r.service or "unknown"
                    if r.payload.get("value") == "0":
                        already = any(o["service"] == svc and o["signal"] == "health_degradation" for o in observations)
                        if not already:
                            observations.append({"service": svc, "signal": "health_degradation", "value": "down"})
        except Exception:
            pass

        # Deduplicate observations by (service, signal)
        seen = set()
        deduped = []
        for o in observations:
            key = (o["service"], o["signal"])
            if key not in seen:
                seen.add(key)
                deduped.append(o)
        observations = deduped

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
