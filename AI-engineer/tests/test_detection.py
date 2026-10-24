import os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path: sys.path.insert(0, ROOT)
from detection.rules import Thresholds, error_rate_spike, latency_spike, log_burst
from detection.grouping import IncidentGrouper

def test_error_rate_spike():
    t = Thresholds()
    assert error_rate_spike(0.5, 0.0, t) is True
    assert error_rate_spike(0.0, 0.0, t) is False

def test_latency_spike():
    t = Thresholds()
    assert latency_spike(10.0, 1.0, t) is True
    assert latency_spike(1.5, 1.0, t) is False

def test_log_burst():
    t = Thresholds(log_error_burst=5)
    assert log_burst(10, t) is True
    assert log_burst(2, t) is False

def test_grouping_cooldown():
    g = IncidentGrouper(cooldown_seconds=10)
    assert g.should_create("k") is True
    assert g.should_create("k") is False
