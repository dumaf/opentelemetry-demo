# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0
"""Unit and fixture tests for incident_tools.hands."""

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import tempfile
import unittest

from incident_tools.hands.adapter import ActionApiAdapter
from incident_tools.hands.approval import ApprovalGate
from incident_tools.hands.executor import HandsExecutor
from incident_tools.hands.kill_switch import KillSwitch, KillSwitchEngagedError
from incident_tools.hands.models import (
    ActionCategory,
    ActionPlan,
    ApprovalDecision,
    compute_plan_digest,
    utc_now_iso,
    VerificationResult,
)
from incident_tools.hands.store import HandsStore
from incident_tools.hands.verifier import RecoveryVerifier


class TestHandsModels(unittest.TestCase):
    def setUp(self):
        self.valid_plan = {
            "incident_id": "inc-001",
            "action_type": ActionCategory.RESTART_SERVICE,
            "target": "payment",
            "parameters": {},
            "reason": "Payment service unresponsive after high connection pool saturation",
            "confidence": 0.95,
            "risk": "low",
            "verification_criteria": {
                "metric": "error_rate",
                "threshold": 0.05,
                "settling_period_seconds": 0.0,
                "min_samples": 2,
            },
        }

    def test_plan_digest_deterministic(self):
        d1 = compute_plan_digest(self.valid_plan)
        d2 = compute_plan_digest(self.valid_plan)
        self.assertEqual(d1, d2)

        # Altering parameter changes digest
        modified = dict(self.valid_plan)
        modified["parameters"] = {"force": True}
        d3 = compute_plan_digest(modified)
        self.assertNotEqual(d1, d3)

    def test_plan_validation_success(self):
        plan = ActionPlan(self.valid_plan, allowed_services={"payment", "checkout"})
        self.assertEqual(plan.incident_id, "inc-001")
        self.assertEqual(plan.target, "payment")
        self.assertEqual(plan.action_type, ActionCategory.RESTART_SERVICE)
        self.assertTrue(len(plan.digest) > 0)

    def test_unsupported_action(self):
        bad = dict(self.valid_plan)
        bad["action_type"] = "delete_database"
        with self.assertRaises(ValueError):
            ActionPlan(bad)

    def test_scale_service_rejected_in_compose(self):
        bad = dict(self.valid_plan)
        bad["action_type"] = ActionCategory.SCALE_SERVICE
        with self.assertRaises(ValueError):
            ActionPlan(bad)

    def test_service_not_allowlisted(self):
        with self.assertRaises(ValueError):
            ActionPlan(self.valid_plan, allowed_services={"checkout"})

    def test_invalid_verification_is_rejected_before_dispatch(self):
        bad = dict(self.valid_plan)
        bad["verification_criteria"] = {"metric": "error_rate", "threshold": 0.05,
                                        "min_samples": 0}
        with self.assertRaises(ValueError):
            ActionPlan(bad, allowed_services={"payment"})


class TestKillSwitch(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.store = HandsStore(self.temp_dir.name)
        self.kill_switch = KillSwitch(self.store)

    def tearDown(self):
        self.store.close()
        self.temp_dir.cleanup()

    def test_initially_not_engaged(self):
        self.assertFalse(self.kill_switch.is_engaged())
        self.kill_switch.check_clear()

    def test_engage_and_reset(self):
        self.kill_switch.engage(operator="alice", reason="High unintended blast radius detected")
        self.assertTrue(self.kill_switch.is_engaged())
        with self.assertRaises(KillSwitchEngagedError):
            self.kill_switch.check_clear()

        # Check persistence across fresh store instance
        store2 = HandsStore(self.temp_dir.name)
        ks2 = KillSwitch(store2)
        self.assertTrue(ks2.is_engaged())
        store2.close()

        # Reset
        self.kill_switch.reset(operator="bob", reason="Incident cleared")
        self.assertFalse(self.kill_switch.is_engaged())
        self.kill_switch.check_clear()


class TestApprovalGate(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.store = HandsStore(self.temp_dir.name)
        self.kill_switch = KillSwitch(self.store)
        self.gate = ApprovalGate(self.store, self.kill_switch)
        self.plan_dict = {
            "incident_id": "inc-002",
            "action_type": ActionCategory.TOGGLE_FEATURE_FLAG,
            "target": "paymentServiceFailure",
            "parameters": {"desired_state": False},
            "reason": "Disable payment failure flag",
            "confidence": 0.99,
            "risk": "low",
            "verification_criteria": {"metric": "error_rate", "threshold": 0.01, "min_samples": 2},
        }
        self.plan = ActionPlan(self.plan_dict)
        self.store.save_plan(self.plan.to_dict())

    def tearDown(self):
        self.store.close()
        self.temp_dir.cleanup()

    def test_unapproved_plan_rejected(self):
        auth, msg = self.gate.verify_authorization(self.plan)
        self.assertFalse(auth)
        self.assertIn("No human approval decision", msg)

    def test_approved_plan_authorized(self):
        self.gate.record_decision(
            incident_id=self.plan.incident_id,
            plan_digest=self.plan.digest,
            decision="approved",
            operator="alice",
        )
        auth, msg = self.gate.verify_authorization(self.plan)
        self.assertTrue(auth)
        self.assertIn("Authorized by 'alice'", msg)

    def test_rejected_plan_denied(self):
        self.gate.record_decision(
            incident_id=self.plan.incident_id,
            plan_digest=self.plan.digest,
            decision="rejected",
            operator="bob",
            reason="Unverified symptom",
        )
        auth, msg = self.gate.verify_authorization(self.plan)
        self.assertFalse(auth)
        self.assertIn("explicitly rejected", msg)

    def test_kill_switch_overrides_approval(self):
        self.gate.record_decision(
            incident_id=self.plan.incident_id,
            plan_digest=self.plan.digest,
            decision="approved",
            operator="alice",
        )
        self.kill_switch.engage(operator="admin", reason="Freeze")
        auth, msg = self.gate.verify_authorization(self.plan)
        self.assertFalse(auth)
        self.assertIn("Kill switch is active", msg)

    def test_expired_approval_rejected(self):
        expired_at = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat().replace("+00:00", "Z")
        self.gate.record_decision(
            incident_id=self.plan.incident_id,
            plan_digest=self.plan.digest,
            decision="approved",
            operator="alice",
            expires_at=expired_at,
        )
        auth, msg = self.gate.verify_authorization(self.plan)
        self.assertFalse(auth)
        self.assertIn("expired", msg)


class TestRecoveryVerifier(unittest.TestCase):
    def test_invalid_criteria_cannot_claim_recovery(self):
        def fake_query(service, metric, start, end):
            self.fail("Invalid verification criteria must not query telemetry")

        verifier = RecoveryVerifier(query_fn=fake_query)
        for criteria in ({"metric": "error_rate", "threshold": 0.05, "min_samples": 0},
                         {"metric": "error_rate", "threshold": float("nan"), "min_samples": 1},
                         {"metric": "unknown", "threshold": 0.05, "min_samples": 1},
                         {"metric": "error_rate", "min_samples": 1}):
            with self.subTest(criteria=criteria):
                res = verifier.verify("inc", "digest", utc_now_iso(), criteria, "payment")
                self.assertEqual(res.verdict, VerificationResult.INCONCLUSIVE)

    def test_recovered_when_samples_below_threshold(self):
        action_time = (datetime.now(timezone.utc) - timedelta(seconds=20)).isoformat().replace("+00:00", "Z")
        def fake_query(service, metric, start, end):
            begin = datetime.fromisoformat(start.replace("Z", "+00:00"))
            return {
                "status": "ok",
                "observations": [{
                    "samples": [
                        {"timestamp": (begin + timedelta(seconds=5)).isoformat(), "value": "0.01"},
                        {"timestamp": (begin + timedelta(seconds=10)).isoformat(), "value": "0.00"},
                    ]
                }],
            }

        verifier = RecoveryVerifier(query_fn=fake_query)
        res = verifier.verify(
            incident_id="inc-1",
            plan_digest="hash123",
            action_time_iso=action_time,
            criteria={"metric": "error_rate", "threshold": 0.05, "min_samples": 2, "settling_period_seconds": 0.0},
            target_service="payment",
        )
        self.assertEqual(res.verdict, VerificationResult.RECOVERED)

    def test_not_recovered_when_threshold_exceeded(self):
        action_time = (datetime.now(timezone.utc) - timedelta(seconds=20)).isoformat().replace("+00:00", "Z")
        def fake_query(service, metric, start, end):
            begin = datetime.fromisoformat(start.replace("Z", "+00:00"))
            return {
                "status": "ok",
                "observations": [{
                    "samples": [
                        {"timestamp": (begin + timedelta(seconds=5)).isoformat(), "value": "0.15"},
                        {"timestamp": (begin + timedelta(seconds=10)).isoformat(), "value": "0.12"},
                    ]
                }],
            }

        verifier = RecoveryVerifier(query_fn=fake_query)
        res = verifier.verify(
            incident_id="inc-1",
            plan_digest="hash123",
            action_time_iso=action_time,
            criteria={"metric": "error_rate", "threshold": 0.05, "min_samples": 2, "settling_period_seconds": 0.0},
            target_service="payment",
        )
        self.assertEqual(res.verdict, VerificationResult.NOT_RECOVERED)


class TestHandsExecutor(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.store = HandsStore(self.temp_dir.name)
        self.kill_switch = KillSwitch(self.store)
        self.gate = ApprovalGate(self.store, self.kill_switch)
        self.adapter = ActionApiAdapter({"mode": "mock"})

        class FakeVerifier:
            def verify(self, incident_id, plan_digest, **kwargs):
                return VerificationResult(VerificationResult.RECOVERED, incident_id, plan_digest,
                                          utc_now_iso(), [], "Mock recovery verdict")

        self.verifier = FakeVerifier()
        self.executor = HandsExecutor(self.store, self.gate, self.kill_switch, self.adapter, self.verifier)

        self.plan_dict = {
            "incident_id": "inc-003",
            "action_type": ActionCategory.RESTART_SERVICE,
            "target": "checkout",
            "parameters": {},
            "reason": "Restart deadlocked checkout service",
            "confidence": 0.90,
            "risk": "medium",
            "verification_criteria": {
                "metric": "error_rate",
                "threshold": 0.05,
                "min_samples": 1,
                "settling_period_seconds": 0.0,
            },
        }
        self.plan = ActionPlan(self.plan_dict, allowed_services={"checkout"})
        self.store.save_plan(self.plan.to_dict())

    def tearDown(self):
        self.store.close()
        self.temp_dir.cleanup()

    def test_dry_run_does_not_mutate_or_record_dispatch(self):
        self.gate.record_decision(
            incident_id=self.plan.incident_id,
            plan_digest=self.plan.digest,
            decision="approved",
            operator="alice",
        )
        res = self.executor.dispatch(self.plan, dry_run=True)
        self.assertTrue(res["success"])
        self.assertEqual(res["status"], "dry_run")
        self.assertFalse(self.store.is_dispatched(self.plan.digest))

    def test_full_execution_and_idempotency(self):
        self.gate.record_decision(
            incident_id=self.plan.incident_id,
            plan_digest=self.plan.digest,
            decision="approved",
            operator="alice",
        )
        res = self.executor.dispatch(self.plan, dry_run=False)
        self.assertTrue(res["success"])
        self.assertEqual(res["status"], "completed")
        self.assertTrue(self.store.is_dispatched(self.plan.digest))

        # Second dispatch of the exact same plan is blocked by idempotency ledger
        res2 = self.executor.dispatch(self.plan, dry_run=False)
        self.assertFalse(res2["success"])
        self.assertEqual(res2["status"], "unauthorized")
        self.assertIn("already been dispatched", res2["message"])

    def test_adapter_exception_is_audited_as_unknown(self):
        self.gate.record_decision(self.plan.incident_id, self.plan.digest, "approved", "alice")

        def fail(**kwargs):
            raise TimeoutError("remote outcome unknown")

        self.adapter.execute = fail
        result = self.executor.dispatch(self.plan)
        self.assertEqual(result["status"], "action_outcome_unknown")
        self.assertTrue(self.store.is_dispatched(self.plan.digest))
        self.assertEqual(self.store.list_audits()[0]["status"], "unknown")
        self.assertIsNone(self.store.get_verification(self.plan.incident_id, self.plan.digest))


if __name__ == "__main__":
    unittest.main()
