"""Synthetic, offline handoff tests; no Docker, Action API, or model network calls."""

from datetime import timedelta
from contextlib import redirect_stdout
from copy import deepcopy
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from incident_tools.brain import extract, load_run
from incident_tools.brain.tests.test_brain import full_run
from incident_tools.f02.boundary import iso, utc_now
from incident_tools.hands.adapter import ActionApiAdapter
from incident_tools.hands.approval import ApprovalGate
from incident_tools.hands.executor import HandsExecutor
from incident_tools.hands.kill_switch import KillSwitch
from incident_tools.hands.models import ActionPlan, VerificationResult, compute_plan_digest
from incident_tools.hands.store import HandsStore
from incident_tools.hands.verifier import RecoveryVerifier
from incident_tools.pipeline import analyze
from incident_tools.pipeline.workflow import watch_eyes
from incident_tools.pipeline.__main__ import main


class FakeRouter:
    def __init__(self, refs, confidence="high"):
        self.refs = refs
        self.confidence = confidence

    def decide(self, messages, remaining):
        return {"status": "diagnosed", "affected_component": "checkout",
                "root_cause_hypothesis": "Checkout container exited while requests failed",
                "supporting_fact_ids": self.refs, "contradicting_fact_ids": [],
                "alternative_hypotheses": [], "confidence": self.confidence,
                "confidence_rationale": "Checkout state, span and log evidence agree",
                "missing_evidence": [], "recommended_next_steps": []}, \
               {"slot": "fixture", "backend": "fixture", "model": "fixture-model"}


def synthetic_run(now):
    data = full_run()
    data["origin"] = "backend"
    data["incident"]["origin"] = "backend"
    data["finished_at"] = iso(now)
    for item in data["evidence"]:
        item["origin"] = "backend"
        if item.get("tool") == "container_health":
            item["observations"][0].update(observed_at=iso(now - timedelta(seconds=30)),
                                            status="exited", running=False, health="unhealthy")
    return data


class TestPipeline(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.now = utc_now()
        self.data = synthetic_run(self.now)
        facts = extract(load_run(self.data))
        self.refs = [fact.fact_id for fact in facts if fact.type in ("span", "log_entry", "container_state")]

    def tearDown(self):
        self.temp.cleanup()

    def test_eyes_brain_to_approved_mock_hands_and_verification(self):
        hands_dir = self.root / "hands"
        output = self.root / "analysis"
        result = analyze(self.data, FakeRouter(self.refs), output, hands_dir, {"checkout"}, self.now)
        self.assertEqual(result["hands_status"], "awaiting_human_approval")
        self.assertEqual(json.loads((output / "brain_report.json").read_text())["incident"]["id"],
                         self.data["incident"]["id"])
        self.assertTrue((output / "brain_report.md").exists())
        store = HandsStore(hands_dir)
        try:
            plan = ActionPlan(store.get_plan(result["plan_digest"]), {"checkout"})
            self.assertEqual(plan.digest, result["plan_digest"])
            self.assertEqual(plan.confidence, "high")
            self.assertEqual(plan.data["verification_criteria"]["service"], "checkout")
            kill = KillSwitch(store)
            gate = ApprovalGate(store, kill)

            class FakeVerifier:
                def verify(self, incident_id, plan_digest, **kwargs):
                    return VerificationResult("recovered", incident_id, plan_digest, iso(utc_now()), [],
                                              "Synthetic post-action evidence")

            executor = HandsExecutor(store, gate, kill, ActionApiAdapter({"mode": "mock"}), FakeVerifier())
            self.assertEqual(executor.dispatch(plan)["status"], "unauthorized")
            self.assertFalse(store.is_dispatched(plan.digest))
            gate.record_decision(plan.incident_id, plan.digest, "approved", "test-operator")
            self.assertEqual(executor.dispatch(plan, dry_run=True)["status"], "dry_run")
            self.assertFalse(store.is_dispatched(plan.digest))
            result = executor.dispatch(plan)
            self.assertTrue(result["success"])
            self.assertEqual(store.get_verification(plan.incident_id, plan.digest)["verdict"], "recovered")
            self.assertEqual(executor.dispatch(plan)["status"], "unauthorized")
        finally:
            store.close()

    def test_eyes_watch_export_automatically_enters_brain(self):
        eyes_dir = self.root / "eyes"
        export_dir = eyes_dir / "incident-run"
        export_dir.mkdir(parents=True)
        (export_dir / "checkpoint1_execution_log.json").write_text(json.dumps(self.data))

        class FakeProcess:
            def __init__(self):
                self.stdout = io.StringIO(json.dumps({"incident": "inc", "artifacts": str(export_dir)}) + "\n")

            def wait(self):
                return 0

            def poll(self):
                return 0

        output = io.StringIO()
        with redirect_stdout(output):
            status = watch_eyes("eyes.toml", eyes_dir, FakeRouter(self.refs),
                                self.root / "analyses", self.root / "hands", {"checkout"},
                                polls=1, launch=lambda *args, **kwargs: FakeProcess())
        self.assertEqual(status, 0)
        self.assertIn('"pipeline_status": "analyzed"', output.getvalue())
        records = list((self.root / "analyses").glob("*/pipeline_handoff.json"))
        self.assertEqual(len(records), 1)
        self.assertEqual(json.loads(records[0].read_text())["hands_status"], "awaiting_human_approval")

    def test_uncertain_or_old_evidence_never_registers_a_plan(self):
        for name, router, now in (("low", FakeRouter(self.refs, "low"), self.now),
                                  ("stale", FakeRouter(self.refs), self.now + timedelta(minutes=10))):
            with self.subTest(name=name):
                hands_dir = self.root / (name + "-hands")
                result = analyze(self.data, router, self.root / name, hands_dir, {"checkout"}, now)
                self.assertEqual(result["hands_status"], "escalated")
                self.assertIsNone(result["plan_digest"])
                self.assertFalse(hands_dir.exists())

    def test_incomplete_eyes_failure_is_preserved_without_model_call_or_plan(self):
        data = deepcopy(self.data)
        data.update(evidence=[], stop_reason='invalid_decision_or_provider_failure',
                    failure={'code': 'invalid_action', 'step': 0})

        class UnusedRouter:
            def decide(inner, *args):
                self.fail('Brain must not call the model without observations')

        result = analyze(data, UnusedRouter(), self.root / 'incomplete', self.root / 'hands',
                         {'checkout'}, self.now)
        self.assertEqual(result['eyes_failure'], {'code': 'invalid_action', 'step': 0})
        self.assertEqual(result['brain_status'], 'escalated')
        self.assertEqual(result['report_validation'], 'valid')
        self.assertEqual(result['reason'], 'Eyes investigation is incomplete')
        self.assertIsNone(result['plan_digest'])
        self.assertFalse((self.root / 'hands').exists())

    def test_explicit_investigation_command_also_enters_brain(self):
        eyes_root = self.root / 'eyes'
        export_dir = eyes_root / 'retry'
        export_dir.mkdir(parents=True)
        (export_dir / 'checkpoint1_execution_log.json').write_text(json.dumps(self.data))
        commands = []

        class Process:
            stdout = io.StringIO(json.dumps({'artifacts': str(export_dir)}) + '\n')
            def wait(inner):
                return 0
            def poll(inner):
                return 0

        def launch(command, **kwargs):
            commands.append(command)
            return Process()

        with redirect_stdout(io.StringIO()):
            status = watch_eyes('eyes.toml', eyes_root, FakeRouter(self.refs), self.root / 'analyses',
                                self.root / 'hands', {'checkout'}, launch=launch,
                                incident_id=self.data['incident']['id'])
        self.assertEqual(status, 0)
        self.assertEqual(commands[0][-3:], ['investigate', '--id', self.data['incident']['id']])
        self.assertEqual(len(list((self.root / 'analyses').glob('*/pipeline_handoff.json'))), 1)

    def test_cli_passes_explicit_incident_to_connected_workflow(self):
        hands_file = self.root / 'hands.toml'
        hands_file.write_text('data_dir = "hands-state"\n[adapter]\nmode = "mock"\n'
                              '[safety]\nservices = ["checkout"]\n')
        with patch('incident_tools.pipeline.__main__.load', return_value=({'models': {}}, {}, 'f02.toml', 'eyes')), \
                patch('incident_tools.pipeline.__main__.Router'), \
                patch('incident_tools.pipeline.__main__.watch_eyes', return_value=0) as workflow:
            status = main(['--eyes-config', 'eyes.toml', '--hands-config', str(hands_file),
                           '--investigate', 'incident-test', '--output-root', str(self.root / 'analyses')])
        self.assertEqual(status, 0)
        self.assertEqual(workflow.call_args.kwargs['incident_id'], 'incident-test')

    def test_plan_digest_binds_reviewed_fields_and_direct_adapter_is_disabled(self):
        result = analyze(self.data, FakeRouter(self.refs), self.root / "analysis", self.root / "hands",
                         {"checkout"}, self.now)
        store = HandsStore(self.root / "hands")
        try:
            plan_data = store.get_plan(result["plan_digest"])
            changed = dict(plan_data, expected_impact="Different impact")
            self.assertNotEqual(compute_plan_digest(changed), result["plan_digest"])
            with self.assertRaises(ValueError):
                store.save_plan(changed)
            plan = ActionPlan(plan_data, {"checkout"})
            gate = ApprovalGate(store, KillSwitch(store))
            gate.record_decision(plan.incident_id, plan.digest, "approved", "test-operator")
            executor = HandsExecutor(store, gate, KillSwitch(store),
                                     ActionApiAdapter({"mode": "local_docker"}), RecoveryVerifier())
            self.assertEqual(executor.dispatch(plan)["status"], "adapter_disabled")
            self.assertFalse(store.is_dispatched(plan.digest))
        finally:
            store.close()

    def test_missing_metric_value_and_no_traffic_cannot_prove_recovery(self):
        action_at = iso(utc_now() - timedelta(seconds=20))
        sample_at = iso(utc_now() - timedelta(seconds=10))

        def missing_value(service, metric, start, end):
            return {"status": "ok", "observations": [{"samples": [{"timestamp": sample_at}]}]}

        result = RecoveryVerifier(missing_value).verify("incident", "digest", action_at,
                                                        {"metric": "error_rate", "min_samples": 1}, "checkout")
        self.assertEqual(result.verdict, "inconclusive")

        def no_traffic(service, metric, start, end):
            value = 0.0 if metric == "request_rate" else 0.01
            return {"status": "ok", "observations": [{"samples": [
                {"timestamp": sample_at, "value": value}]}]}

        result = RecoveryVerifier(no_traffic).verify("incident", "digest", action_at,
                                                     {"metric": "error_rate", "threshold": 0.05,
                                                      "min_samples": 1, "min_requests": 10}, "checkout")
        self.assertEqual(result.verdict, "inconclusive")


if __name__ == "__main__":
    unittest.main()
