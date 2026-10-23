#!/usr/bin/env bash
# Run the cluster's containers locally (see compose.yaml).
#   bash deploy/local/run.sh          # Cognito login, like the cluster
#   AUTH=dev bash deploy/local/run.sh # dev login (pick a demo user), no password
set -euo pipefail
cd "$(dirname "$0")"
PROFILE=${AWS_PROFILE:-team-admin}
AUTH=${AUTH:-cognito}

# Settings: services/.env without the CLI profile (containers get short-lived keys instead).
grep -v '^AWS_PROFILE=' ../../services/.env | sed "s/^RF_AUTH_MODE=.*/RF_AUTH_MODE=$AUTH/" > .env.rf
aws configure export-credentials --profile "$PROFILE" --format env-no-export > .env.aws
echo "AWS_REGION=ap-northeast-2" >> .env.aws

export VITE_AUTH_MODE=$AUTH
export VITE_COGNITO_CLIENT_ID=$(grep '^RF_COGNITO_CLIENT_ID=' .env.rf | cut -d= -f2)
docker compose up --build -d
echo "open http://localhost:8088  (stop: docker compose -f deploy/local/compose.yaml down)"
