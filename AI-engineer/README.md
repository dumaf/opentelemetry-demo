# Eyes — OpenTelemetry Demo Integration, FaultCLI, and Blind Fault Detection

Independent incident-observation and fault-detection application living entirely under `AI-engineer/`. It uses the existing OpenTelemetry Demo as the system under test.

## Discovered faults

20 feature flags in `src/flagd/demo.flagd.json`, e.g. `cartFailure`, `paymentFailure`, `adFailure`, `emailMemoryLeak`, `kafkaQueueProblems`, `productCatalogFailure`, `recommendationCacheFailure`, etc. Full inventory: `artifacts/fault_inventory.json`.

## Install

```bash
cd AI-engineer
python -m pip install -e .
cd frontend && npm install
```

## Configure model

Copy `.env.model.example` to `.env.model` and fill credentials. Keep `.env.model` out of version control (gitignored).

```dotenv
MODEL_PROVIDER=openai
MODEL_NAME=gpt-4o-mini
MODEL_API_KEY=...
MODEL_BASE_URL=https://api.openai.com/v1
```

## FaultCLI

```bash
faultcli list
faultcli inspect cartFailure
faultcli status
faultcli trigger cartFailure --variant 100%
faultcli reset cartFailure
faultcli reset --all
faultcli run cartFailure --duration 30 --variant 100%
faultcli history
faultcli doctor
```

FaultCLI uses the flagd-ui REST API (`/api/read`, `/api/write`) to mutate flags; it never edits `src/flagd/demo.flagd.json`. Baselines are recorded on first use.

## Run backend

```bash
cd AI-engineer
uvicorn backend.app.main:app --port 8090
```

## Run frontend

```bash
cd AI-engineer/frontend
npm run dev   # http://localhost:5173
```

## Telemetry backends used

- Prometheus `http://localhost:9090` (PromQL)
- Jaeger `http://localhost:16686` (trace query API)
- OpenSearch `http://localhost:9200` index `otel-logs`
- OTel Collector `http://localhost:4318`

Requires the demo's observability layer (`compose.observability.yaml`) for Jaeger/Prometheus/OpenSearch. Without it, signals are labeled unavailable (not fabricated).

## Blind detection

`detection/engine.py` runs periodic cycles (default 30s), applies thresholds to metrics/logs/traces/health, groups observations, dedups via cooldown (default 5 min). It does not consult fault-control history. Incidents stored in SQLite.

## Eyes workflow

`incidents/eyes.py` collects evidence, calls the cloud LLM with evidence only (hidden fault identity excluded), validates evidence references, persists report.

## Human approval workflow

Every state-changing action requires explicit human approval. The backend classifies actions (read_only vs state_changing). State-changing actions create a pending approval; the user approves/rejects via the Approvals page (or /api/approvals), then executes. Kill switch blocks all new state-changing operations. Audit log records all decisions.

## Incident dashboard

The Dashboard shows service health, active/recent incidents, pending approvals, active faults, telemetry availability. Each incident links to details/evidence/diagnosis.

## Brain workflow

`brain/diagnoser.py` performs root-cause diagnosis using the required JSON schema, excluding hidden fault identity from the prompt. `brain/validator.py` validates JSON, evidence refs, confidence, timestamps. `brain/evaluator.py` compares diagnosis with hidden expected outcome only after diagnosis is saved (separate evaluation). Endpoints under `/api/brain`. UI: Run Brain button, diagnosis list, view, evaluate.

## Tests

```bash
cd AI-engineer
python -m pytest -q
cd frontend && npm run build
```

## Limitations

- Demo must be running with observability layer for telemetry; otherwise signals unavailable.
- flagd-ui REST write rewrites whole config (concurrency risk; serialized in CLI).
- No auth on local backend (local demo use only).
- Live LLM verification requires user credentials in `.env.model`; otherwise mocked/unverified.
- Integration tests against live demo not run in this environment (demo not running).
