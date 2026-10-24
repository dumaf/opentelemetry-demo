"""Detection thresholds and rules."""
from __future__ import annotations

from dataclasses import dataclass

@dataclass
class Thresholds:
    error_rate_abs: float = 0.05          # absolute 5xx ratio
    error_rate_sigma: float = 3.0
    latency_factor: float = 2.0           # p99 multiplier
    log_error_burst: int = 1             # errors per window per service (demo traffic is very low)
    min_consecutive: int = 2
    cooldown_seconds: int = 300

def error_rate_spike(current: float, baseline: float, t: Thresholds) -> bool:
    return current >= t.error_rate_abs and current >= baseline + (baseline * 0.5 + 0.02)

def latency_spike(current: float, baseline: float, t: Thresholds) -> bool:
    if baseline <= 0:
        return current > 0 and current > 1.0
    return current >= baseline * t.latency_factor

def log_burst(count: int, t: Thresholds) -> bool:
    return count >= t.log_error_burst
