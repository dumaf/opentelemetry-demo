import os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path: sys.path.insert(0, ROOT)
from llm.validation import parse_response, validate_refs
from llm.client import LLMClient, LLMConfig

def test_parse_response_json():
    r = parse_response('{"a": 1}')
    assert r["a"] == 1

def test_parse_response_fenced():
    r = parse_response('```json\n{"a": 2}\n```')
    assert r["a"] == 2

def test_validate_refs():
    bundle = {"evidence_refs": ["E1", "E2"]}
    resp = {"evidence_refs": ["E1", "E9"]}
    assert validate_refs(resp, bundle) == ["E9"]

def test_redaction():
    c = LLMClient(LLMConfig())
    c.config.api_key = "sk-abcdefghijklmnopqrstuvwxyz"
    out = c.redact("key sk-abcdefghijklmnopqrstuvwxyz here")
    assert "[REDACTED]" in out
