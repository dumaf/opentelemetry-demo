# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0
"""Recovery verification using post-remediation evidence."""

import time
from typing import Callable

from incident_tools.f02.boundary import finite, timestamp

from .models import VerificationResult, utc_now_iso


class RecoveryVerifier:
    def __init__(self, query_fn: Callable[[str, str, str, str], dict] | None = None):
        self.query_fn = query_fn

    def verify(
        self,
        incident_id: str,
        plan_digest: str,
        action_time_iso: str,
        criteria: dict,
        target_service: str,
        sleep_fn: Callable[[float], None] = time.sleep,
    ) -> VerificationResult:
        now_iso = utc_now_iso()
        try:
            settling_seconds = finite(criteria.get("settling_period_seconds", 0.0))
            metric_name = criteria["metric"]
            threshold = finite(criteria["threshold"])
            min_samples = int(criteria["min_samples"])
            required_requests = finite(criteria.get("min_requests", 0))
            if (settling_seconds < 0 or min_samples < 1 or required_requests < 0 or
                    metric_name not in ("error_rate", "latency_p95_ms")):
                raise ValueError("Unsupported verification criteria")
        except (KeyError, TypeError, ValueError, OverflowError):
            return VerificationResult(
                verdict=VerificationResult.INCONCLUSIVE, incident_id=incident_id,
                plan_digest=plan_digest, verified_at=now_iso, observed_samples=[],
                summary="Verification criteria are missing or invalid.",
            )
        if settling_seconds > 0:
            sleep_fn(settling_seconds)

        now_iso = utc_now_iso()

        if not self.query_fn:
            return VerificationResult(
                verdict=VerificationResult.INCONCLUSIVE,
                incident_id=incident_id,
                plan_digest=plan_digest,
                verified_at=now_iso,
                observed_samples=[],
                summary="No telemetry query provider configured for verification.",
            )

        try:
            res = self.query_fn(target_service, metric_name, action_time_iso, now_iso)
        except Exception as ex:
            return VerificationResult(
                verdict=VerificationResult.INCONCLUSIVE,
                incident_id=incident_id,
                plan_digest=plan_digest,
                verified_at=now_iso,
                observed_samples=[],
                summary=f"Failed to query verification telemetry: {ex}",
            )

        if res.get("status") != "ok":
            return VerificationResult(
                verdict=VerificationResult.INCONCLUSIVE,
                incident_id=incident_id,
                plan_digest=plan_digest,
                verified_at=now_iso,
                observed_samples=[],
                summary=f"Telemetry returned non-ok status: {res.get('status')} ({res.get('warnings', [])})",
            )

        observations = res.get("observations", [])
        if not observations:
            return VerificationResult(
                verdict=VerificationResult.INCONCLUSIVE,
                incident_id=incident_id,
                plan_digest=plan_digest,
                verified_at=now_iso,
                observed_samples=[],
                summary="No metric observations returned for verification window.",
            )

        samples = observations[0].get("samples", [])
        post_action_samples = []
        try:
            action_time = timestamp(action_time_iso)
            end_time = timestamp(now_iso)
            seen = set()
            for sample in samples:
                sample_time = timestamp(sample["timestamp"])
                if action_time < sample_time <= end_time and sample_time not in seen:
                    finite(sample["value"])
                    post_action_samples.append(sample)
                    seen.add(sample_time)
        except (KeyError, TypeError, ValueError):
            return VerificationResult(
                verdict=VerificationResult.INCONCLUSIVE, incident_id=incident_id,
                plan_digest=plan_digest, verified_at=now_iso, observed_samples=[],
                summary="Verification samples have missing, invalid, or non-finite values.",
            )

        if len(post_action_samples) < min_samples:
            return VerificationResult(
                verdict=VerificationResult.INCONCLUSIVE,
                incident_id=incident_id,
                plan_digest=plan_digest,
                verified_at=now_iso,
                observed_samples=post_action_samples,
                summary=f"Insufficient post-action samples: got {len(post_action_samples)}, required {min_samples}.",
            )

        if required_requests:
            try:
                rate = self.query_fn(target_service, "request_rate", action_time_iso, now_iso)
                rate_samples = rate["observations"][0]["samples"]
                usable_rates = [finite(sample["value"]) for sample in rate_samples
                                if action_time < timestamp(sample["timestamp"]) <= end_time]
                if rate["status"] != "ok" or not usable_rates or usable_rates[-1] * 120 < finite(required_requests):
                    raise ValueError("Insufficient continuing traffic")
            except (KeyError, IndexError, TypeError, ValueError, OverflowError):
                return VerificationResult(
                    verdict=VerificationResult.INCONCLUSIVE, incident_id=incident_id,
                    plan_digest=plan_digest, verified_at=now_iso, observed_samples=post_action_samples,
                    summary="Continuing request traffic could not be established after the action.",
                )

        values = [finite(s["value"]) for s in post_action_samples]
        operator = criteria.get("comparison", "<=")
        if operator not in ("<=", "<", "=="):
            return VerificationResult(
                verdict=VerificationResult.INCONCLUSIVE, incident_id=incident_id,
                plan_digest=plan_digest, verified_at=now_iso, observed_samples=post_action_samples,
                summary="Unsupported verification comparison.",
            )

        all_passed = True
        for val in values:
            if operator == "<=" and not (val <= threshold):
                all_passed = False
            elif operator == "<" and not (val < threshold):
                all_passed = False
            elif operator == "==" and not (val == threshold):
                all_passed = False

        if all_passed:
            verdict = VerificationResult.RECOVERED
            summary = f"All {len(values)} post-action samples met threshold {operator} {threshold} (values: {values})."
        else:
            verdict = VerificationResult.NOT_RECOVERED
            summary = f"One or more post-action samples breached threshold {operator} {threshold} (values: {values})."

        return VerificationResult(
            verdict=verdict,
            incident_id=incident_id,
            plan_digest=plan_digest,
            verified_at=now_iso,
            observed_samples=post_action_samples,
            summary=summary,
        )
