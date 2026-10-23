#!/usr/bin/env bash
# Run all four backend services locally against the AWS resources in services/.env.
#   bash scripts/dev.sh                    # Cognito login
#   RF_AUTH_MODE=dev bash scripts/dev.sh   # accept dev tokens (web: npm run dev:devauth)
#   WORKER=0 bash scripts/dev.sh           # omit OCR while changing shared processing code or working UI-only
# Shared workers may run on each PC with the same approved OCR/common code and real Bedrock settings.
# Never attach mock or unreviewed OCR/common changes to the shared queue (docs/worker.md).
# Web: `npm --prefix web run dev` proxies /api, /chat, /preprocess to these ports.
# No --reload: on Windows its worker processes outlive Ctrl+C and keep the ports bound.
set -euo pipefail
cd "$(dirname "$0")/.."

uv run uvicorn api_service.main:app --port 8000 &
uv run uvicorn chat_service.main:app --port 8001 &
uv run uvicorn preprocess_service.main:app --port 8002 &
if [ "${WORKER:-1}" != 0 ]; then uv run ocr-worker & fi

trap 'kill 0' INT TERM EXIT
wait
