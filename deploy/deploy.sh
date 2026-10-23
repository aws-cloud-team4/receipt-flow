#!/usr/bin/env bash
# Deploy everything to the EKS cluster from this PC (after `terraform -chdir=infra/terraform/eks apply`).
#   bash deploy/deploy.sh               # test deploy: 1 node, fixed replicas (eks node_count=1)
#   SCALING=1 bash deploy/deploy.sh     # final deploy: + Cluster Autoscaler (nodes 2→3) and KEDA (ocr-worker 1→5)
#                                       #   create the cluster with -var node_count=2 for this
# Needs: aws (profile team-admin = your IAM user, not root), docker, kubectl, helm.
# Does: kubeconfig → AWS Load Balancer Controller → build and push 5 images to ECR → apply deploy/k8s
#       → wait for the pods and the ALB → point CloudFront (HTTPS) at the ALB → print the address.
#       Safe to run again (it updates in place).
set -euo pipefail
cd "$(dirname "$0")/.."
source deploy/versions.sh

PROFILE=${AWS_PROFILE:-team-admin}
REGION=ap-northeast-2
CLUSTER=receipt-flow-dev
TAG=$(git rev-parse --short=12 HEAD)$(git diff --quiet || echo -dirty)
SERVICES=(api-service chat-service preprocess-service ocr-worker)

for tool in aws docker kubectl helm terraform timeout; do
  command -v $tool >/dev/null || { echo "missing $tool (helm: winget install Helm.Helm)"; exit 1; }
done
if ! timeout 20s docker info --format '{{.ServerVersion}}' >/dev/null; then
  echo "Docker engine is not ready. Check Docker Desktop before deploying (docs/aws.md: troubleshooting)." >&2
  exit 1
fi
if aws sts get-caller-identity --profile "$PROFILE" --query Arn --output text | grep -q ':root$'; then
  echo "signed in as the root account; sign in as your IAM user (aws login --profile $PROFILE)"; exit 1
fi
ACCOUNT=$(aws sts get-caller-identity --profile "$PROFILE" --query Account --output text)
ECR=$ACCOUNT.dkr.ecr.$REGION.amazonaws.com

echo "== version compatibility"
K8S=$(aws eks describe-cluster --name "$CLUSTER" --region "$REGION" --profile "$PROFILE" --query cluster.version --output text)
CLIENT=$(kubectl version --client -o json)
CLIENT_MAJOR=$(printf '%s\n' "$CLIENT" | sed -n 's/.*"major": *"\([^"]*\)".*/\1/p')
CLIENT_MINOR=$(printf '%s\n' "$CLIENT" | sed -n 's/.*"minor": *"\([^"]*\)".*/\1/p')
check_deploy_versions "$K8S" "$CLIENT_MAJOR" "$CLIENT_MINOR"

echo "== kubeconfig"
aws eks update-kubeconfig --region $REGION --name $CLUSTER --profile "$PROFILE"

echo "== AWS Load Balancer Controller (creates the ALB for the ingress)"
VPC_ID=$(terraform -chdir=infra/terraform/eks output -raw vpc_id)
helm repo add eks https://aws.github.io/eks-charts >/dev/null 2>&1 || true
helm repo update eks >/dev/null
helm upgrade --install aws-load-balancer-controller eks/aws-load-balancer-controller -n kube-system \
  --version "$ALB_CHART_VERSION" \
  --set clusterName=$CLUSTER --set serviceAccount.name=aws-load-balancer-controller \
  --set region=$REGION --set vpcId="$VPC_ID" --set replicaCount=1 --set keepTLSSecret=true --wait
# Its webhook certificate is regenerated on install/upgrade; restart so the running pod serves the one
# the API server now trusts (otherwise: "x509: certificate signed by unknown authority").
kubectl -n kube-system rollout restart deployment aws-load-balancer-controller
kubectl -n kube-system rollout status deployment aws-load-balancer-controller --timeout=180s

if [ "${SCALING:-0}" = 1 ]; then
  echo "== autoscalers: KEDA (ocr-worker on queue length) and Cluster Autoscaler (nodes)"
  # Pod Identity roles: infra/terraform/admin scaling.tf, associations: infra/terraform/eks
  helm repo add kedacore https://kedacore.github.io/charts >/dev/null 2>&1 || true
  helm repo add autoscaler https://kubernetes.github.io/autoscaler >/dev/null 2>&1 || true
  helm repo update kedacore autoscaler >/dev/null
  helm upgrade --install keda kedacore/keda -n keda --create-namespace \
    --version "$KEDA_CHART_VERSION" --set serviceAccount.operator.name=keda-operator --wait
  helm upgrade --install cluster-autoscaler autoscaler/cluster-autoscaler -n kube-system \
    --version "$AUTOSCALER_CHART_VERSION" \
    --set autoDiscovery.clusterName=$CLUSTER --set awsRegion=$REGION \
    --set rbac.serviceAccount.name=cluster-autoscaler --set image.tag="$AUTOSCALER_IMAGE_VERSION" \
    --set extraArgs.balance-similar-node-groups=true --set extraArgs.skip-nodes-with-system-pods=false \
    --set extraArgs.scale-down-unneeded-time=5m --wait
fi

echo "== images ($TAG)"
# Keep the ECR login in a throwaway Docker config file. On Windows the credential helpers next to
# docker.exe reject the long ECR token ("The stub received bad data") and the CLI picks them up from
# PATH even with an empty config, so call docker.exe by its full path with that folder off PATH.
export DOCKER_CONFIG=$(mktemp -d)
trap 'rm -rf "$DOCKER_CONFIG"' EXIT
echo '{}' > "$DOCKER_CONFIG/config.json"
DOCKER_DIR=$(dirname "$(command -v docker)")
if [ -x "$DOCKER_DIR/docker.exe" ]; then
  DOCKER_EXE="$DOCKER_DIR/docker.exe"
  NO_HELPERS_PATH=$(printf %s "$PATH" | tr ':' '\n' | grep -vF "$DOCKER_DIR" | paste -sd: -)
  docker() { PATH="$NO_HELPERS_PATH" "$DOCKER_EXE" "$@"; } # only docker loses that folder (kubectl lives there too)
fi
aws ecr get-login-password --region $REGION --profile "$PROFILE" | docker login -u AWS --password-stdin "$ECR"
for s in "${SERVICES[@]}"; do
  docker build --build-arg SERVICE=$s -t "$ECR/receipt-flow/$s:$TAG" services/
  docker push "$ECR/receipt-flow/$s:$TAG"
done
CLIENT_ID=$(grep 'RF_COGNITO_CLIENT_ID:' deploy/k8s/config.yaml | awk '{print $2}')
docker build --build-arg VITE_COGNITO_CLIENT_ID="$CLIENT_ID" -t "$ECR/receipt-flow/web:$TAG" web/
docker push "$ECR/receipt-flow/web:$TAG"

echo "== manifests"
WORK=$(mktemp -d)
cp -r deploy/k8s/. "$WORK"
sed -i "s/newTag: latest/newTag: $TAG/" "$WORK/kustomization.yaml"
kubectl apply -k "$WORK"
rm -rf "$WORK"
kubectl -n receipt-flow rollout status deploy --timeout=300s
if [ "${SCALING:-0}" = 1 ]; then
  kubectl apply -f deploy/k8s-scaling/
fi

echo "== ALB address (takes 1-3 minutes the first time)"
for _ in $(seq 1 60); do
  HOST=$(kubectl -n receipt-flow get ingress receipt-flow -o jsonpath='{.status.loadBalancer.ingress[0].hostname}' 2>/dev/null || true)
  [ -n "$HOST" ] && break
  sleep 5
done
[ -n "${HOST:-}" ] || { echo "no ALB yet: kubectl -n receipt-flow describe ingress receipt-flow"; exit 1; }
for _ in $(seq 1 60); do
  curl -fsS "http://$HOST/healthz" >/dev/null 2>&1 && break
  sleep 5
done
echo "== HTTPS (CloudFront → ALB; a few minutes when the ALB changed)"
terraform -chdir=infra/terraform/edge init -input=false >/dev/null
terraform -chdir=infra/terraform/edge apply -input=false -auto-approve   -var aws_profile="$PROFILE" -var alb_dns_name="$HOST"
echo "open $(terraform -chdir=infra/terraform/edge output -raw url)   (phones: this https address)"
