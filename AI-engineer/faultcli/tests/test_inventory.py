import os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path: sys.path.insert(0, ROOT)
from eyes_core.inventory import build_inventory

def test_inventory_non_empty():
    inv = build_inventory()
    assert len(inv) >= 20

def test_cart_failure_variants():
    inv = {f["flag_key"]: f for f in build_inventory()}
    assert "cartFailure" in inv
    assert "100%" in inv["cartFailure"]["available_variants"]
    assert inv["cartFailure"]["configured_default"] == "off"

def test_variant_validation():
    inv = {f["flag_key"]: f for f in build_inventory()}
    assert "on" in inv["adFailure"]["available_variants"]
    assert "bogus" not in inv["adFailure"]["available_variants"]
