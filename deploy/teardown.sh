#!/usr/bin/env bash
# Before `terraform -chdir=infra/terraform/eks destroy`: remove what Kubernetes created in AWS.
#   bash deploy/teardown.sh
# The ALB (and its security groups) belong to the load balancer controller, not to Terraform; if the
# cluster goes first they are left behind, keep costing money and block deleting the VPC.
set -euo pipefail
cd "$(dirname "$0")/.."
PROFILE=${AWS_PROFILE:-team-admin}

echo "== delete the app (the controller removes the ALB with the ingress)"
kubectl -n receipt-flow delete ingress receipt-flow --ignore-not-found --wait=true
kubectl delete -k deploy/k8s --ignore-not-found --wait=true || true

echo "== wait until no receipt-flow ALB is left"
for _ in $(seq 1 60); do
  LEFT=$(aws elbv2 describe-load-balancers --profile "$PROFILE" --region ap-northeast-2 \
    --query "LoadBalancers[?contains(LoadBalancerName, 'receiptf')].LoadBalancerName" --output text)
  [ -z "$LEFT" ] && break
  echo "  still there: $LEFT"; sleep 10
done
[ -z "${LEFT:-}" ] || { echo "ALB still exists; check the EC2 console before destroying"; exit 1; }
echo "done. now: terraform -chdir=infra/terraform/eks destroy -var aws_profile=$PROFILE"
echo "CloudFront (infra/terraform/edge) stays: it costs nothing idle and keeps the same https address"
echo "then check the EC2 console for leftover load balancers, EBS volumes and network interfaces"
