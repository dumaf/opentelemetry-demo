# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0
"""Main coordinator for Hands: gatekeeping, dispatch, audit, and verification."""

import uuid

from incident_tools.f02.boundary import timestamp

from .adapter import ActionApiAdapter
from .approval import ApprovalGate
from .kill_switch import KillSwitch, KillSwitchEngagedError
from .models import ActionPlan, ActionAttempt, VerificationResult, utc_now_iso
from .store import HandsStore
from .verifier import RecoveryVerifier


class HandsExecutor:
    def __init__(
        self,
        store: HandsStore,
        approval_gate: ApprovalGate,
        kill_switch: KillSwitch,
        adapter: ActionApiAdapter,
        verifier: RecoveryVerifier,
    ):
        self.store = store
        self.approval_gate = approval_gate
        self.kill_switch = kill_switch
        self.adapter = adapter
        self.verifier = verifier

    def dispatch(self, plan: ActionPlan, dry_run: bool = False) -> dict:
        now_iso = utc_now_iso()

        if self.adapter.mode not in ("mock", "http") or (self.adapter.mode == "http" and not self.adapter.live_enabled):
            return {"success": False, "status": "adapter_disabled", "message": "A configured Action API is required; direct Docker and faultctl actions are disabled."}
        valid_until = plan.data.get("valid_until")
        if valid_until and timestamp(now_iso) >= timestamp(valid_until):
            return {"success": False, "status": "stale_plan", "message": "Plan evidence expired; analyze fresh Eyes evidence before approval."}

        # 1. Verification of Human Authorization
        authorized, reason = self.approval_gate.verify_authorization(plan, current_iso=now_iso)
        if not authorized:
            return {
                "success": False,
                "status": "unauthorized",
                "message": reason,
                "incident_id": plan.incident_id,
                "plan_digest": plan.digest,
            }

        # 2. Check kill switch immediately before dispatch
        if self.kill_switch.is_engaged():
            return {
                "success": False,
                "status": "halted_by_kill_switch",
                "message": "Kill switch is engaged. Execution halted.",
                "incident_id": plan.incident_id,
                "plan_digest": plan.digest,
            }

        # 3. Handle Dry Run
        if dry_run:
            return {
                "success": True,
                "status": "dry_run",
                "message": "Dry run validated successfully. No mutations performed.",
                "incident_id": plan.incident_id,
                "plan_digest": plan.digest,
                "planned_action": plan.to_dict(),
            }

        # 4. Generate Idempotency Key & Record in Ledger
        attempt_id = f"att-{uuid.uuid4().hex[:12]}"
        self.store.record_dispatch(
            incident_id=plan.incident_id,
            plan_digest=plan.digest,
            attempt_id=attempt_id,
            dispatched_at=now_iso,
            status="dispatched",
        )

        # 5. Execute Action through Adapter
        try:
            exec_res = self.adapter.execute(
                action_type=plan.action_type,
                target=plan.target,
                parameters=plan.parameters,
                idempotency_key=attempt_id,
            )
        except Exception:
            exec_res = {
                "dispatched_at": now_iso, "status": "unknown", "duration_ms": 0.0,
                "response_data": {},
                "error_message": "Action outcome unknown; inspect the action system before any new plan.",
            }

        # 6. Save Audit Record
        audit_record = {
            "attempt_id": attempt_id,
            "incident_id": plan.incident_id,
            "plan_digest": plan.digest,
            "action_type": plan.action_type,
            "target": plan.target,
            "parameters": plan.parameters,
            "dispatched_at": exec_res["dispatched_at"],
            "status": exec_res["status"],
            "duration_ms": exec_res["duration_ms"],
            "response_data": exec_res["response_data"],
            "error_message": exec_res["error_message"],
        }
        self.store.save_audit(audit_record)

        if exec_res["status"] != "ok":
            return {
                "success": False,
                "status": "action_outcome_unknown" if exec_res["status"] == "unknown" else "action_failed",
                "message": exec_res.get("error_message") or "Action API did not confirm completion.",
                "incident_id": plan.incident_id,
                "plan_digest": plan.digest,
                "attempt": audit_record,
            }

        # 7. Verification of Recovery
        criteria = plan.data.get("verification_criteria", {})
        verif_res = self.verifier.verify(
            incident_id=plan.incident_id,
            plan_digest=plan.digest,
            action_time_iso=exec_res["dispatched_at"],
            criteria=criteria,
            target_service=criteria.get("service", plan.target),
        )
        self.store.save_verification(verif_res.to_dict())

        return {
            "success": verif_res.verdict == VerificationResult.RECOVERED,
            "status": "completed",
            "incident_id": plan.incident_id,
            "plan_digest": plan.digest,
            "action_attempt": audit_record,
            "verification": verif_res.to_dict(),
            "rollback_executed": False,
            "rollback_result": None,
        }
