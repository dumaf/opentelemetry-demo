#!/usr/bin/env bash
# Start Eyes backend + frontend (run from AI-engineer/)
export FLAGD_UI_BASE_URL=http://localhost:32918
export PROMETHEUS_BASE_URL=http://localhost:9090
export JAEGER_BASE_URL=http://localhost:32911
export OPENSEARCH_BASE_URL=http://localhost:32905
export OTEL_COLLECTOR_HTTP_URL=http://localhost:4318
cd "$(dirname "$0")"
python -m uvicorn backend.app.main:app --port 8090 --host 0.0.0.0 &
cd frontend && npm run dev
