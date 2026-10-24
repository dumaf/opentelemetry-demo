import os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path: sys.path.insert(0, ROOT)
from brain.validator import validate

def _valid_diag():
    return {"incident_id":"inc_1","detection_mode":"controlled","summary":"cart failure","affected_services":["cart"],"symptoms":[{"description":"5xx spike","evidence_refs":["E1"]}],"root_cause":{"description":"cartFailure flag","status":"hypothesized","evidence_refs":["E1"]},"causal_analysis":[{"claim":"x","reasoning":"y","evidence_refs":["E1"]}],"timeline":[{"timestamp":"2026-01-01T00:00:00+00:00","event":"spike","evidence_refs":["E1"]}],"confidence":{"score":0.7,"rationale":"ok"},"alternative_hypotheses":[{"description":"alt","supporting_evidence":[],"contradicting_evidence":[]}],"missing_evidence":[],"recommended_next_steps":["check logs"],"telemetry_sources":["prometheus"],"llm_metadata":{"provider":"p","model":"m"}}

def test_validate_ok():
    bundle = {"evidence_refs": ["E1"]}
    ok, errs = validate(_valid_diag(), bundle)
    assert ok, errs

def test_validate_bad_confidence():
    d = _valid_diag(); d["confidence"]["score"] = 1.5
    bundle = {"evidence_refs": ["E1"]}
    ok, errs = validate(d, bundle)
    assert not ok

def test_validate_unknown_ref():
    d = _valid_diag(); d["symptoms"][0]["evidence_refs"] = ["E9"]
    bundle = {"evidence_refs": ["E1"]}
    ok, errs = validate(d, bundle)
    assert not ok

def test_validate_bad_status():
    d = _valid_diag(); d["root_cause"]["status"] = "foo"
    bundle = {"evidence_refs": ["E1"]}
    ok, errs = validate(d, bundle)
    assert not ok
