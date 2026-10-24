# Hands: Action Execution, Safety Gate & Recovery Verification

Hands provides a draft Checkpoint 3 implementation. Live acceptance requires an approved Action API and observed recovery; offline tests alone do not complete M6.

It provides an approval gate, audit store, Action API client, and telemetry verifier for proposed remediation plans. The supplied mock mode is for offline testing; no live Action API has been validated.

---

## 1. Safety Architecture

```
[ Proposed Plan (JSON) ]
          │
          ▼
   compute_plan_digest()  --> Canonical SHA-256 Hash
          │
          ▼
   ApprovalGate           --> Requires explicit human decision bound to Plan Digest
          │
          ▼
   KillSwitch Check       --> Durable emergency stop latch (checked at dispatch & in-flight)
          │
          ▼
   Idempotency Ledger     --> Prevents duplicate dispatches in SQLite
          │
          ▼
   ActionApiAdapter       --> Restricted to allowlisted operations & targets
          │
          ▼
   RecoveryVerifier       --> Measures post-remediation telemetry (fresh samples only)
          │
     ┌────┴────────────┐
     ▼                 ▼
[ Recovered ]    [ Not Recovered ]
                       │
                       ▼
                    Escalation
```

### Safety Guarantees
1. **Approval Gate**: The model has no action credentials. A proposed action needs an operator approval bound to the plan SHA-256 digest before dispatch.
2. **Durable Kill Switch**: A persistent latch stored in SQLite blocks dispatch across restarts until an operator resets it. It cannot cancel an action already accepted by a remote API.
3. **Idempotency & Replay Prevention**: Dispatches are recorded before execution. Re-dispatching a plan is blocked locally; remote API idempotency and timeout outcome still depend on the supplied API contract.
4. **Target & Parameter Allowlisting**: Services and action types are constrained to the configured allowlist. Arbitrary shell commands and unsupported actions (like scaling in Docker Compose) are strictly rejected.
5. **Fresh Evidence Verification**: Recovery requires distinct post-action evaluation timestamps and continuing traffic when the plan asks for it. Underlying metric source freshness still needs live validation.

---

## 2. Supported Action Types

| Action Type | Target | Description |
| :--- | :--- | :--- |
| `restart_service` | Allowlisted service name | Proposed by the integration pipeline; mockable offline. An approved HTTP Action API is required for live dispatch. |
| `toggle_feature_flag`, `throttle_load_generator` | Flag or load generator | Present in the inherited plan vocabulary; live dispatch is disabled. |
| `scale_service` | Service name | Rejected by plan validation. |

---

## 3. Configuration

Copy `operator.example.toml` to a dedicated location:
```sh
cp incident_tools/hands/operator.example.toml /tmp/hands-operator.toml
```

Key sections:
* `data_dir`: Directory for `hands.sqlite` (plans, approvals, audit logs, and kill latch).
* `adapter.mode`: `"mock"` (default, offline testing) or `"http"` (approved Action API only). The inherited `local_docker` path is disabled because it bypasses that API.
* HTTP live mode requires `enable_live_actions = true`, an explicit approved `api_url`, and `api_token_env` naming an exported token. An official endpoint, response and idempotency contract must be checked before use.
* `safety.services`: List of permissible target services.
* Each plan's `verification_criteria` sets the settling delay, affected service, metric, threshold, minimum samples and traffic requirement.

---

## 4. CLI Usage

### Check Status & Kill Switch
```sh
python3 -m incident_tools.hands --config /tmp/hands-operator.toml status
```

### Register a Proposed Remediation Plan
```sh
python3 -m incident_tools.hands --config /tmp/hands-operator.toml plan --file sample_plan.json
```
Output returns the canonical `plan_digest`.

### Explicit Human Approval
```sh
python3 -m incident_tools.hands --config /tmp/hands-operator.toml approve \
  --digest <PLAN_DIGEST> \
  --operator "oncall-alice" \
  --reason "Verified deadlock in checkout logs" \
  --ttl-minutes 15
```

### Dry Run (Validation Without Mutation)
```sh
python3 -m incident_tools.hands --config /tmp/hands-operator.toml dispatch \
  --digest <PLAN_DIGEST> \
  --dry-run
```

### Dispatch Approved Action & Verify Recovery
```sh
python3 -m incident_tools.hands --config /tmp/hands-operator.toml dispatch \
  --digest <PLAN_DIGEST>
```
With the example configuration this uses the mock adapter; the action result is synthetic. Live dispatch needs the approved Action API configuration described above. An inconclusive verification does not establish recovery. Automatic rollback is disabled.

### Emergency Stop (Kill Switch)
```sh
python3 -m incident_tools.hands --config /tmp/hands-operator.toml kill \
  --operator "oncall-alice" \
  --reason "Unexpected error rate spike in payment"
```

### Reset Kill Switch
```sh
python3 -m incident_tools.hands --config /tmp/hands-operator.toml reset-kill \
  --operator "oncall-alice" \
  --reason "Root cause resolved and blast radius contained"
```

---

## 5. Offline Verification

Run the test suite:
```sh
python3 -m unittest discover -s incident_tools/hands/tests -v
```
