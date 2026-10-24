import os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path: sys.path.insert(0, ROOT)
from llm.client import LLMConfig, LLMClient

def test_missing_credentials_raises():
    cfg = LLMConfig()
    cfg.api_key = ""
    cfg.model = ""
    c = LLMClient(cfg)
    try:
        c.chat([{"role":"user","content":"hi"}])
        assert False, "should raise"
    except RuntimeError:
        pass
