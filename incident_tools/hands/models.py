# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0
"""Data models, canonical hashing, and plan validation for Hands."""

from datetime import datetime, timezone
import hashlib
import json
import math
import re

from incident_tools.f02.boundary import identifier


class ActionCategory:
    RESTART_SERVICE = "restart_service"
    TOGGLE_FEATURE_FLAG = "toggle_feature_flag"
    THROTTLE_LOAD_GENERATOR = "throttle_load_generator"
    SCALE_SERVICE = "scale_service"

    ALL = {
        RESTART_SERVICE,
        TOGGLE_FEATURE_FLAG,
        THROTTLE_LOAD_GENERATOR,
        SCALE_SERVICE,
    }


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def compute_plan_digest(plan: dict) -> str:
    canonical = {key: value for key, value in plan.items() if key not in ("plan_digest", "created_at")}
    encoded = json.dumps(canonical, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def validate_plan_structure(plan: dict, allowed_services: set[str] | None = None) -> None:
    if not isinstance(plan, dict):
        raise ValueError("Plan must be a dictionary")

    required_fields = [
        "incident_id",
        "action_type",
        "target",
        "parameters",
        "reason",
        "confidence",
        "risk",
        "verification_criteria",
    ]
    for field in required_fields:
        if field not in plan:
            raise ValueError(f"Missing required plan field: {field}")

    action_type = plan["action_type"]
    if action_type not in ActionCategory.ALL:
        raise ValueError(f"Unsupported action type: {action_type}. Must be one of {sorted(ActionCategory.ALL)}")

    if action_type == ActionCategory.SCALE_SERVICE:
        raise ValueError("scale_service is unsupported in Docker Compose mode")

    target = plan["target"]
    if not isinstance(target, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", target):
        raise ValueError(f"Invalid target identifier: {target}")

    if allowed_services is not None and action_type == ActionCategory.RESTART_SERVICE:
        if target not in allowed_services:
            raise ValueError(f"Target service '{target}' is not in allowlisted services")

    confidence = plan["confidence"]
    if confidence not in ("low", "medium", "high"):
        if isinstance(confidence, bool):
            raise ValueError("Confidence must be categorical or a number between 0 and 1")
        try:
            numeric = float(confidence)
        except (TypeError, ValueError):
            raise ValueError("Confidence must be categorical or a number between 0 and 1") from None
        if not math.isfinite(numeric) or not 0.0 <= numeric <= 1.0:
            raise ValueError("Confidence must be categorical or a number between 0 and 1")

    risk = plan["risk"]
    if risk not in ("low", "medium", "high"):
        raise ValueError(f"Risk must be 'low', 'medium', or 'high', got '{risk}'")

    params = plan["parameters"]
    if not isinstance(params, dict):
        raise ValueError("Parameters must be a dictionary")

    if action_type == ActionCategory.TOGGLE_FEATURE_FLAG:
        if "desired_state" not in params or not isinstance(params["desired_state"], bool):
            raise ValueError("toggle_feature_flag requires boolean 'desired_state' parameter")

    if action_type == ActionCategory.THROTTLE_LOAD_GENERATOR:
        if "spawn_rate" in params:
            float(params["spawn_rate"])
        if "users" in params:
            int(params["users"])

    crit = plan["verification_criteria"]
    if not isinstance(crit, dict):
        raise ValueError("Verification criteria must be a dictionary")
    if crit.get("metric") not in ("error_rate", "latency_p95_ms"):
        raise ValueError("Verification metric must be error_rate or latency_p95_ms")
    try:
        threshold = float(crit["threshold"])
        min_samples = int(crit["min_samples"])
        min_requests = float(crit.get("min_requests", 0))
        settling = float(crit.get("settling_period_seconds", 0))
    except (KeyError, TypeError, ValueError, OverflowError):
        raise ValueError("Verification criteria require numeric threshold and sample count") from None
    if (not all(math.isfinite(value) for value in (threshold, min_requests, settling)) or
            threshold < 0 or min_samples < 1 or min_requests < 0 or settling < 0):
        raise ValueError("Verification criteria contain invalid limits")
    service = crit.get("service", target)
    if not identifier(service):
        raise ValueError("Invalid verification service")
    if allowed_services is not None and service not in allowed_services:
        raise ValueError("Verification service is outside the allowlist")


class ActionPlan:
    def __init__(self, data: dict, allowed_services: set[str] | None = None):
        validate_plan_structure(data, allowed_services)
        self.data = dict(data)
        self.plan_digest = compute_plan_digest(self.data)
        self.data["plan_digest"] = self.plan_digest
        if "created_at" not in self.data:
            self.data["created_at"] = utc_now_iso()

    @property
    def incident_id(self) -> str:
        return self.data["incident_id"]

    @property
    def action_type(self) -> str:
        return self.data["action_type"]

    @property
    def target(self) -> str:
        return self.data["target"]

    @property
    def parameters(self) -> dict:
        return self.data["parameters"]

    @property
    def confidence(self) -> float | str:
        value = self.data["confidence"]
        return value if value in ("low", "medium", "high") else float(value)

    @property
    def digest(self) -> str:
        return self.plan_digest

    def to_dict(self) -> dict:
        return dict(self.data)


class ApprovalDecision:
    def __init__(
        self,
        incident_id: str,
        plan_digest: str,
        decision: str,
        operator: str,
        reason: str = "",
        approved_at: str | None = None,
        expires_at: str | None = None,
    ):
        if decision not in ("approved", "rejected"):
            raise ValueError("Decision must be 'approved' or 'rejected'")
        if not operator or not isinstance(operator, str):
            raise ValueError("Operator identifier must be a non-empty string")
        if not plan_digest or not isinstance(plan_digest, str):
            raise ValueError("Plan digest must be a valid non-empty string")

        self.incident_id = incident_id
        self.plan_digest = plan_digest
        self.decision = decision
        self.operator = operator
        self.reason = reason
        self.approved_at = approved_at or utc_now_iso()
        self.expires_at = expires_at

    def is_valid(self, expected_digest: str, current_iso: str | None = None) -> bool:
        if self.decision != "approved":
            return False
        if self.plan_digest != expected_digest:
            return False
        if self.expires_at:
            now_iso = current_iso or utc_now_iso()
            if now_iso > self.expires_at:
                return False
        return True

    def to_dict(self) -> dict:
        return {
            "incident_id": self.incident_id,
            "plan_digest": self.plan_digest,
            "decision": self.decision,
            "operator": self.operator,
            "reason": self.reason,
            "approved_at": self.approved_at,
            "expires_at": self.expires_at,
        }


class ActionAttempt:
    def __init__(
        self,
        attempt_id: str,
        incident_id: str,
        plan_digest: str,
        action_type: str,
        target: str,
        parameters: dict,
        dispatched_at: str,
        status: str,
        response_data: dict | None = None,
        duration_ms: float = 0.0,
        error_message: str | None = None,
    ):
        self.attempt_id = attempt_id
        self.incident_id = incident_id
        self.plan_digest = plan_digest
        self.action_type = action_type
        self.target = target
        self.parameters = parameters
        self.dispatched_at = dispatched_at
        self.status = status
        self.response_data = response_data or {}
        self.duration_ms = duration_ms
        self.error_message = error_message

    def to_dict(self) -> dict:
        return {
            "attempt_id": self.attempt_id,
            "incident_id": self.incident_id,
            "plan_digest": self.plan_digest,
            "action_type": self.action_type,
            "target": self.target,
            "parameters": self.parameters,
            "dispatched_at": self.dispatched_at,
            "status": self.status,
            "response_data": self.response_data,
            "duration_ms": self.duration_ms,
            "error_message": self.error_message,
        }


class VerificationResult:
    RECOVERED = "recovered"
    PARTIAL = "partial"
    NOT_RECOVERED = "not_recovered"
    INCONCLUSIVE = "inconclusive"

    def __init__(
        self,
        verdict: str,
        incident_id: str,
        plan_digest: str,
        verified_at: str,
        observed_samples: list[dict],
        summary: str,
    ):
        if verdict not in (self.RECOVERED, self.PARTIAL, self.NOT_RECOVERED, self.INCONCLUSIVE):
            raise ValueError(f"Invalid verification verdict: {verdict}")

        self.verdict = verdict
        self.incident_id = incident_id
        self.plan_digest = plan_digest
        self.verified_at = verified_at
        self.observed_samples = observed_samples
        self.summary = summary

    def to_dict(self) -> dict:
        return {
            "verdict": self.verdict,
            "incident_id": self.incident_id,
            "plan_digest": self.plan_digest,
            "verified_at": self.verified_at,
            "observed_samples": self.observed_samples,
            "summary": self.summary,
        }
