"""Tests for server-side approval enforcement and human-in-the-loop workflow."""
import time
import pytest
from eyes_core.approval import (
    propose, approve, reject, execute, get_approval,
    is_kill_switch_enabled, set_kill_switch, classify
)
from eyes_core.storage import fetch_all

@pytest.fixture(autouse=True)
def reset_kill_switch_state():
    set_kill_switch(False)
    yield
    set_kill_switch(False)

def test_action_classification():
    assert classify("trigger_fault") == "state_changing"
    assert classify("reset_fault") == "state_changing"
    assert classify("reset_all_faults") == "state_changing"
    assert classify("execute_remediation") == "state_changing"
    assert classify("view_dashboard") == "read_only"
    assert classify("view_logs") == "read_only"
    assert classify("unknown_action_xyz") == "unknown"

def test_propose_creates_pending_approval():
    proposal = propose(
        action="trigger_fault",
        target="cartFailure",
        params={"variant": "50%"},
        reason="Test injection",
        risk="high",
        reversible=True
    )
    assert proposal["status"] == "pending"
    aid = proposal["approval_id"]
    record = get_approval(aid)
    assert record is not None
    assert record["status"] == "pending"
    assert record["action"] == "trigger_fault"
    assert record["target"] == "cartFailure"
    assert record["params"] == {"variant": "50%"}

def test_agent_cannot_approve_own_action():
    proposal = propose("reset_fault", "cartFailure", {"to": "off"})
    aid = proposal["approval_id"]
    with pytest.raises(ValueError, match="Agent or system cannot approve actions"):
        approve(aid, actor="agent")
    with pytest.raises(ValueError, match="Agent or system cannot approve actions"):
        approve(aid, actor="system")
    with pytest.raises(ValueError, match="Agent or system cannot approve actions"):
        approve(aid, actor="llm")
    # Verify still pending
    assert get_approval(aid)["status"] == "pending"

def test_unapproved_action_cannot_execute():
    proposal = propose("trigger_fault", "adFailure", {"variant": "on"})
    aid = proposal["approval_id"]
    executed = False
    def mock_executor():
        nonlocal executed
        executed = True
        return {"done": True}

    with pytest.raises(ValueError, match="Approval not approved: pending"):
        execute(aid, {"variant": "on"}, mock_executor, actor="operator")
    assert not executed
    assert get_approval(aid)["status"] == "pending"

def test_human_approval_and_execution_lifecycle():
    proposal = propose("reset_fault", "paymentFailure", {"to": "off"})
    aid = proposal["approval_id"]

    # 1. Human approves
    decided = approve(aid, actor="human_operator")
    assert decided["status"] == "approved"
    assert decided["decided_by"] == "human_operator"

    # 2. Execute approved action
    executed = False
    def mock_executor():
        nonlocal executed
        executed = True
        return {"action": "reset_fault", "target": "paymentFailure", "recovered": True}

    res = execute(aid, {"to": "off"}, mock_executor, actor="human_operator")
    assert executed
    assert res["status"] == "completed"
    assert res["result"]["recovered"] is True

    # 3. Cannot execute twice (repeated/concurrent protection)
    with pytest.raises(ValueError, match="Approval not approved: completed"):
        execute(aid, {"to": "off"}, mock_executor, actor="human_operator")

def test_parameter_tampering_blocked():
    proposal = propose("trigger_fault", "emailMemoryLeak", {"variant": "100x"})
    aid = proposal["approval_id"]
    approve(aid, actor="human")

    # Try executing with different parameters than approved
    def mock_executor():
        return {}

    with pytest.raises(ValueError, match="Parameters do not match approved proposal"):
        execute(aid, {"variant": "10000x"}, mock_executor, actor="human")

def test_rejected_action_cannot_execute():
    proposal = propose("trigger_fault", "cartFailure", {"variant": "100%"})
    aid = proposal["approval_id"]
    reject(aid, actor="safety_officer", reason="High traffic window")
    assert get_approval(aid)["status"] == "rejected"

    # Cannot approve after rejection
    with pytest.raises(ValueError, match="Approval not pending: rejected"):
        approve(aid, actor="human")

    # Cannot execute after rejection
    with pytest.raises(ValueError, match="Approval not approved: rejected"):
        execute(aid, {"variant": "100%"}, lambda: {}, actor="human")

def test_kill_switch_blocks_execution():
    proposal = propose("reset_fault", "shipping", {"to": "off"})
    aid = proposal["approval_id"]
    approve(aid, actor="human")

    set_kill_switch(True, reason="Emergency drill")
    try:
        assert is_kill_switch_enabled() is True
        with pytest.raises(ValueError, match="Kill switch is enabled"):
            execute(aid, {"to": "off"}, lambda: {}, actor="human")
    finally:
        set_kill_switch(False, reason="End drill")

def test_audit_log_records_events():
    proposal = propose("trigger_fault", "adHighCpu", {"variant": "on"})
    aid = proposal["approval_id"]
    approve(aid, actor="audited_human")

    logs = fetch_all("audit_log", where="approval_id=?", params=(aid,))
    event_types = [l["event_type"] for l in logs]
    assert "proposal_created" in event_types
    assert "approval_granted" in event_types
