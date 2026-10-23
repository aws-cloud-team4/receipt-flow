#!/usr/bin/env bash
# Reviewed together for EKS 1.35; change these pins only after compatibility checks.
EKS_VERSION=1.35
ALB_CHART_VERSION=3.6.0
KEDA_CHART_VERSION=2.21.0
AUTOSCALER_CHART_VERSION=9.59.0
AUTOSCALER_IMAGE_VERSION=v1.35.2

check_deploy_versions() {
  local server=$1 client_major=$2 client_minor=${3%%+*}
  if [ "$server" != "$EKS_VERSION" ]; then
    echo "EKS $server is not the reviewed version $EKS_VERSION; review deploy/versions.sh first." >&2
    return 1
  fi
  if [[ "$client_major" != 1 || ! "$client_minor" =~ ^[0-9]+$ ]]; then
    echo "Cannot verify kubectl version: $client_major.$client_minor" >&2
    return 1
  fi
  local server_minor=${EKS_VERSION#*.}
  if (( client_minor < server_minor - 1 || client_minor > server_minor + 1 )); then
    echo "kubectl 1.$client_minor is outside the supported range for EKS $EKS_VERSION (one minor either side)." >&2
    return 1
  fi
}
