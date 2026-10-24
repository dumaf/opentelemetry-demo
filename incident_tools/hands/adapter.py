# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0
"""Action API Adapter with mock and explicitly enabled HTTP modes."""

import json
import os
import time
from urllib import error, parse, request

from incident_tools.f02.boundary import NoRedirect

from .models import ActionCategory, utc_now_iso


class ActionApiAdapter:
    def __init__(self, config: dict):
        self.config = config
        self.mode = config.get("mode", "mock")
        self.live_enabled = config.get("enable_live_actions", False) is True
        self.base_url = config.get("api_url", "http://localhost:8080/action/api").rstrip("/")
        self.timeout_seconds = float(config.get("timeout_seconds", 10.0))
        self.compose_project = config.get("compose_project", "opentelemetry-demo")
        self.allowed_services = set(config.get("services", []))
        self.mock_responses: dict[str, dict] = {}
        self.opener = request.build_opener(request.ProxyHandler({}), NoRedirect())
        self.api_token = None
        if self.mode == "http" and self.live_enabled:
            endpoint = parse.urlsplit(config.get("api_url", ""))
            if not endpoint.hostname or endpoint.username or endpoint.password or endpoint.query or endpoint.fragment or \
                    not (endpoint.scheme == "https" or endpoint.scheme == "http" and
                         endpoint.hostname in ("localhost", "127.0.0.1")):
                raise ValueError("Live Action API must use HTTPS or loopback HTTP")
            env_name = config.get("api_token_env")
            self.api_token = os.environ.get(env_name, "") if isinstance(env_name, str) else ""
            if not self.api_token:
                raise ValueError("Live Action API requires an environment token")

    def execute(self, action_type: str, target: str, parameters: dict, idempotency_key: str) -> dict:
        start_time = time.perf_counter()
        dispatched_at = utc_now_iso()

        if action_type not in ActionCategory.ALL:
            raise ValueError(f"Action type '{action_type}' is not supported")

        if action_type == ActionCategory.SCALE_SERVICE:
            raise ValueError("scale_service is unsupported in Docker Compose environments")
        if self.mode == "local_docker":
            raise ValueError("Direct Docker, faultctl, and Locust actions are disabled")
        if self.mode == "http" and (not self.live_enabled or action_type != ActionCategory.RESTART_SERVICE):
            raise ValueError("Only an explicitly enabled Action API restart is supported live")

        if self.mode == "mock":
            res = self._execute_mock(action_type, target, parameters, idempotency_key)
        elif self.mode == "http":
            res = self._execute_http(action_type, target, parameters, idempotency_key)
        else:
            raise ValueError(f"Unknown adapter mode: {self.mode}")

        duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
        return {
            "attempt_id": idempotency_key,
            "action_type": action_type,
            "target": target,
            "parameters": parameters,
            "dispatched_at": dispatched_at,
            "duration_ms": duration_ms,
            "status": res.get("status", "ok"),
            "response_data": res.get("data", {}),
            "error_message": res.get("error"),
        }

    def _execute_mock(self, action_type: str, target: str, parameters: dict, key: str) -> dict:
        if key in self.mock_responses:
            return self.mock_responses[key]
        if action_type in self.mock_responses:
            return self.mock_responses[action_type]
        return {
            "status": "ok",
            "data": {
                "message": f"Mock executed {action_type} for {target}",
                "operation": action_type,
                "target": target,
                "parameters": parameters,
            },
        }

    def _execute_http(self, action_type: str, target: str, parameters: dict, idempotency_key: str) -> dict:
        url = f"{self.base_url}/{action_type}"
        payload = json.dumps({
            "target": target,
            "parameters": parameters,
            "idempotency_key": idempotency_key,
        }).encode("utf-8")

        req = request.Request(
            url,
            data=payload,
            headers={
                "Content-Type": "application/json",
                "Idempotency-Key": idempotency_key,
                "Authorization": "Bearer " + self.api_token,
            },
            method="POST",
        )

        try:
            with self.opener.open(req, timeout=self.timeout_seconds) as resp:
                raw = resp.read(65537)
                if len(raw) > 65536:
                    raise ValueError("Action API response too large")
                body = json.loads(raw.decode("utf-8"))
                return {"status": "ok", "data": body}
        except error.HTTPError as ex:
            return {"status": "error", "error": f"Action API returned HTTP {ex.code}"}
        except Exception as ex:
            return {"status": "error", "error": str(ex)}
