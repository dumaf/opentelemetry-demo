# Eyes → Brain → Hands integration

This branch builds on `main`'s Eyes/F02 implementation. Eyes now includes a bounded
decision-envelope correction and explicit failure codes; F02 is unchanged. The pipeline reads an Eyes
`checkpoint1_execution_log.json`, runs Brain's fact extraction, diagnosis,
claim validation and draft report builder, then prepares a Hands plan only for a
fresh, directly observed stopped container supported by a high-confidence
diagnosis. The plan is registered for human review. No model has a mutation tool,
and analysis never dispatches an action.

## Run the connected watcher

Run from the repository root in Ubuntu WSL, with the model key exported and
Eyes/F02 operator configurations pointing at the live backends. Copy the Hands
example to a separate TOML and set its `f02_config` and `data_dir` to dedicated
operator paths. The example leaves Hands in `mock` mode.

```bash
cp incident_tools/hands/operator.example.toml /tmp/hands-operator.toml
python3 -B -m incident_tools.pipeline \
  --eyes-config /tmp/eyes-operator/eyes.toml \
  --hands-config /tmp/hands-operator.toml \
  --watch --output-root /tmp/eyes-brain-hands-analyses
```

Eyes keeps its existing deterministic alert polling, incident deduplication,
adaptive investigation and artifact export. The wrapper reads each completed
Eyes execution record, runs Brain, then registers only an eligible Hands plan.
It prints Eyes poll/export events and each pipeline handoff. `--polls 1` limits
the watcher to one Eyes poll for a smoke test; zero runs until interrupted.
Nothing is dispatched by the watcher.

The watcher only picks up queued incidents. To retry a queued or incomplete
investigation explicitly and carry its new export through Brain and the Hands
handoff, use the saved incident ID:

```bash
python3 -B -m incident_tools.pipeline \
  --eyes-config /tmp/eyes-operator/eyes.toml \
  --hands-config /tmp/hands-operator.toml \
  --investigate INCIDENT_ID \
  --output-root /tmp/eyes-brain-hands-retries
```

This starts a new investigation attempt for that incident, preserves earlier
exports, and retains the existing operator lock and action gates. Finished or
interrupted `running` investigations cannot be retried through this option.
The handoff's `eyes_failure` contains the new Eyes failure metadata, or `null`
for a successful attempt or a legacy export without that field.

## Analyze one existing Eyes incident

Run from the repository root in Ubuntu WSL, with `OPENAI_API_KEY` exported. Use
an Eyes record from a completed live investigation. Configure a separate Hands
TOML first; its example uses `mock` mode and a separate SQLite directory.

```bash
cp incident_tools/hands/operator.example.toml /tmp/hands-operator.toml
# Set f02_config to /tmp/eyes-operator/f02.toml and choose a new data_dir.
python3 -B -m incident_tools.pipeline \
  --eyes-log /tmp/eyes-operator/runs/RUN/report/checkpoint1_execution_log.json \
  --eyes-config /tmp/eyes-operator/eyes.toml \
  --hands-config /tmp/hands-operator.toml \
  --output-dir /tmp/eyes-brain-hands-analysis-01
```

The output directory must not already exist. It contains `brain_diagnosis.json`,
`brain_validation.json`, `brain_report.json`, `brain_report.md`, and
`pipeline_handoff.json`. An eligible case also contains `hands_plan.json`, with
its digest registered in the configured Hands store. An escalation/no-plan case
returns exit code 2 and never creates a Hands store. Brain's JSON is an internal
draft contract; the organiser's official schema has not been supplied.

Only a fresh backend-origin Eyes run ending in `model_finished` can produce a
plan. Brain must return a high categorical confidence diagnosis, its claims and
report must pass validation, and a cited container state for the affected
component must show `exited`, `dead`, or `restarting`. Paused containers, latency
alone, missing evidence, and old runs produce a report without an action plan.
The narrow plan is a **proposal**, not a confirmed remedy. It expires in five
minutes and binds its target, evidence IDs, expected impact, risk and recovery
criteria into the approved digest.

## Human-controlled Hands continuation

Inspect `brain_report.md` and `hands_plan.json`. For a registered plan in mock
mode, the existing Hands CLI supplies the approval, dry-run, kill switch,
dispatch ledger and verification stages:

```bash
python3 -B -m incident_tools.hands --config /tmp/hands-operator.toml status
python3 -B -m incident_tools.hands --config /tmp/hands-operator.toml approve \
  --digest PLAN_DIGEST --operator YOUR_NAME --reason "Reviewed evidence and plan"
python3 -B -m incident_tools.hands --config /tmp/hands-operator.toml dispatch \
  --digest PLAN_DIGEST --dry-run
```

Mock dispatch is appropriate only for an offline exercise; its action is
synthetic even if the verifier queries real telemetry. The analysis command
does not approve or dispatch. `reject` and
`kill` remain available independently through the Hands CLI.

Live dispatch is disabled by default. The inherited direct Docker/faultctl/
Locust adapter is disabled, as it bypasses the designated Action API and may
modify demo files. To enable an actual action, an approved Action API contract,
endpoint, authentication token, target policy, idempotency/status semantics and
operator authorization are still needed. The HTTP adapter currently accepts
only a restart operation, requires `enable_live_actions = true` and
`api_token_env`, and does not claim a verified live Action API integration.
Neither an API response nor a mock verdict satisfies Checkpoint 3. Recovery
requires fresh post-action telemetry and continuing request traffic; an
unavailable or inadequate result is inconclusive. Automatic rollback is
disabled until a separately approved inverse action is implemented.

## Offline checks

```bash
python3 -B -m unittest discover -s incident_tools/pipeline/tests -q
python3 -B -m unittest discover -s incident_tools/brain/tests -q
python3 -B -m unittest discover -s incident_tools/hands/tests -q
```

The pipeline test uses synthetic F02-shaped Eyes evidence and a mock model/
adapter. It proves the software handoff and negative gates, not a live incident,
real diagnosis accuracy, official JSON compliance, or verified recovery.
