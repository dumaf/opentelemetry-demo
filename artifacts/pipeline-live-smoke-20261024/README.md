# Eyes → Brain → Hands live integration smoke

This run uses the existing demo telemetry and `gpt-4.1-mini`. It does not inject a fault or dispatch an action. Hands remains in mock mode, and the pipeline registers a plan only if its strict evidence gates pass.

## What was observed

- F02 could query current frontend request-rate and p95 latency metrics from Prometheus, plus logs, traces, and container health in the live preflight.
- The isolated Eyes detector configuration in `eyes-frontend.toml` monitored `frontend` at a 1,000 ms p95 threshold, two consecutive breaches, and ten requests per two-minute rate window.
- On 2026-10-24, six detect-only polls created `incident-80d8eb19642b48978fb771bcb09a97dd` exactly once. The triggering p95 was 3,629.411764705883 ms, supported by `f02-a3d9f3e90a00fafc9457f9bd`. The incident remains queued in `/tmp/eyes-brain-hands-frontend-20261024/eyes`.
- This is detection of an observed latency symptom, not evidence of a particular root cause or a practice-fault injection.
- The OpenAI environment key is available in the operator's interactive Ubuntu shell but not in the separate noninteractive WSL process used to prepare this run. The live model-backed continuation must be launched from that shell.

## Continue from the Ubuntu shell

From the repository root, with `OPENAI_API_KEY` exported:

```bash
test -n "${OPENAI_API_KEY:-}" || { echo 'OPENAI_API_KEY is missing'; exit 1; }
python3 -B -m incident_tools.pipeline \
  --eyes-config artifacts/pipeline-live-smoke-20261024/eyes-frontend.toml \
  --hands-config artifacts/pipeline-live-smoke-20261024/hands-frontend.toml \
  --watch --polls 1 \
  --output-root /tmp/eyes-brain-hands-frontend-20261024/analyses \
  | tee /tmp/eyes-brain-hands-frontend-20261024/pipeline.out
```

The watcher should consume the queued Eyes incident, export an execution log, call Brain, and write a `pipeline_handoff.json`. Inspect the newest analysis directory and verify `brain_diagnosis.json`, `brain_validation.json`, `brain_report.json`, `brain_report.md`, and `pipeline_handoff.json` exist. A Hands plan is not expected for latency alone; `hands_status: escalated` is a valid safety outcome. Do not run Hands `dispatch` for this smoke.

## Limits

The existing checkout practice configuration was not usable for this run: request coverage was below its ten-request minimum, and intermittent undefined p95 samples made the metric result partial. Frontend had sufficient natural traffic, so this test changed no load-generator setting. The observed frontend threshold breach predates any injected fault. Full practice-incident and live Hands acceptance remain separate work.

## First connected attempt and retry

The first connected attempt exported `incident-80d8eb19642b48978fb771bcb09a97dd-0bc638ee` with zero observations. Its saved model response used `action: "query_metrics"` instead of the required `action: "tool"`. The provider did respond; Eyes rejected the decision envelope before executing F02. Brain escalated without a model call because it had no observation facts. The Hands handoff correctly reported `Eyes investigation is incomplete` and registered no plan.

The implementation now makes the enum explicit, permits one bounded envelope correction, and records specific failure codes. Retry the incomplete incident from the Ubuntu shell with the API key exported:

```bash
set -o pipefail
python3 -B -m incident_tools.pipeline \
  --eyes-config artifacts/pipeline-live-smoke-20261024/eyes-frontend.toml \
  --hands-config artifacts/pipeline-live-smoke-20261024/hands-frontend.toml \
  --investigate incident-80d8eb19642b48978fb771bcb09a97dd \
  --output-root /tmp/eyes-brain-hands-frontend-20261024/retries \
  | tee /tmp/eyes-brain-hands-frontend-20261024/retry.out
```

Live success of this retry has not yet been established. Inspect the new Eyes execution log and Brain report, not only the `pipeline_status: analyzed` event. A model-finished Eyes run with usable observations is required; a Hands escalation remains appropriate when no supported remediation is justified.
