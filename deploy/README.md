# EKS 배포 절차 (통합·데모 주간에만)

## 0. 먼저 이 PC에서 컨테이너로 확인 (EKS 생성 없음)

클러스터에 올릴 이미지 5개를 그대로 이 PC에서 띄우고, nginx가 ALB처럼 경로를 나눕니다 (`deploy/local`).
실제 AWS 리소스(`services/.env`)를 씁니다. 같은 PC에서는 컨테이너 실행 전 로컬 개발 백엔드(`scripts/dev.sh`)를 종료해 실행 환경을 중복하지 않습니다. 다른 PC의 워커는 [동일 코드·실제 모델 조건](../docs/worker.md)을 만족하면 함께 실행할 수 있습니다.
EKS 생성 비용은 없지만 실제 Bedrock 등 AWS 사용료는 발생할 수 있습니다. mock·부하 검사는 공용 큐에 연결하지 않고 별도 테스트 환경에서 진행합니다 ([워커 검증 절차](../docs/worker.md#ocr공통-코드나-모델을-수정할-때)).

```bash
bash deploy/local/run.sh             # Cognito 로그인 → http://localhost:8088
AUTH=dev bash deploy/local/run.sh    # 로컬 컨테이너 검증 전용: 데모 사용자 선택 로그인
docker compose -f deploy/local/compose.yaml down
```

`AUTH=dev`는 로컬 검증용 dev 인증 이미지를 빌드합니다. 실제 배포는 기본 Cognito 설정으로 별도 빌드하며 로컬 dev 이미지를 재사용하거나 ECR에 올리지 않습니다.

## 1. 배포 (시연·리허설 날만, 팀 합의 후)

기본 Kubernetes 버전은 **1.35**입니다. 배포 전 [버전·지원 상태](../docs/aws.md#배포-eks--두-방식)를 확인하세요. 표준 지원 종료 전에 버전과 비용을 다시 확인하세요.

배포 도구 구성은 `deploy/versions.sh`에 고정합니다: ALB 차트 3.6.0, KEDA 차트 2.21.0, Autoscaler 차트 9.59.0·이미지 v1.35.2. `deploy.sh`는 실제 클러스터가 1.35인지, kubectl이 허용 범위(1.34~1.36)인지 먼저 검사합니다. 호환 검토 없이 차트 최신 버전으로 올리지 마세요. [배포 구성과 검증 범위](../docs/aws.md#배포-구성).

EKS는 시간당 비용이 나므로 필요할 때 만들고 **같은 날** 지웁니다. 기준: 컨트롤 플레인 $0.10/h + t3.medium 1대 + ALB + 공인 IP (약 $0.20/h). NAT 게이트웨이는 쓰지 않습니다 (노드는 공인 서브넷).
두 가지 방식이 있습니다:

| | 테스트·리허설 | 최종 배포 (발표) |
|---|---|---|
| 노드 | 1대 (`node_count=1`, 기본) | 2대로 시작, 최대 3대 (`-var node_count=2`) |
| 자동 확장 | 없음 (HPA만, 부하가 없으면 그대로) | Cluster Autoscaler(노드) + KEDA(큐 길이 → ocr-worker 1~5개) + HPA(api·chat·preprocess) |
| 배포 명령 | `bash deploy/deploy.sh` | `SCALING=1 bash deploy/deploy.sh` |
| 비용 | 약 $0.20/h | 약 $0.25~0.30/h |
필요한 도구: `aws`(프로필 `team-admin` = 본인 IAM 사용자, 루트 금지), `docker`, `kubectl`, `helm`(`winget install Helm.Helm`).

| 단계 | 명령 |
|---|---|
| 1. 기본 리소스 (S3·SQS·DynamoDB·Cognito·ECR) — 이미 있음, 코드가 바뀌었으면 | `terraform -chdir=infra/terraform/base apply` |
| 2. IAM 역할·정책 — 코드가 바뀌었으면 | `terraform -chdir=infra/terraform/admin apply -var aws_profile=team-admin` |
| 3. EKS 클러스터 (약 15분) — 최종 배포는 `-var node_count=2` 추가 | `terraform -chdir=infra/terraform/eks apply -var aws_profile=team-admin -var 'admin_principal_arns=["arn:aws:iam::431777499129:user/<팀원>"]'` |
| 4. 연결·ALB 컨트롤러·(최종: 자동 확장 설치)·이미지 빌드/업로드·배포·HTTPS 연결·주소 출력 | `bash deploy/deploy.sh` (최종: `SCALING=1 bash deploy/deploy.sh`) |

`deploy.sh`는 다시 실행해도 됩니다 (현재 커밋으로 이미지를 다시 올리고 갱신).
**자동 배포:** 클러스터가 켜져 있는 동안 `main`에 머지하면 GitHub Actions `deploy`가 새 이미지로 바꿔 줍니다 (클러스터가 없으면 건너뜀). 처음 한 번은 `deploy.sh`로 ALB 컨트롤러·자동 확장·HTTPS를 깔아야 하고, 저장소 Secret `AWS_DEPLOY_ROLE_ARN`이 필요합니다 (`admin` 스택의 `github_repo`를 저장소 이름으로 apply → 출력 `github_deploy_role_arn`). 접속은 끝에 출력되는 **`https://….cloudfront.net` 주소**로 합니다 (휴대폰 카메라는 HTTPS에서만 동작). `http://<ALB 주소>`는 확인용입니다.
**HTTPS:** `deploy.sh` 마지막에 CloudFront(`infra/terraform/edge`)가 새 ALB를 가리키게 바꾸고 `https://….cloudfront.net` 주소를 출력합니다. 휴대폰은 이 주소로 접속합니다. 도메인이 필요 없고, 사용량이 적어 무료 범위입니다.
CloudFront는 정리 때 지우지 않습니다 — 켜 둬도 비용이 없고 다음 배포에도 **같은 주소**를 씁니다 (클러스터가 없을 때는 502).
S3 업로드 허용 주소에 ALB·CloudFront 주소 패턴이 들어 있어 따로 고칠 것이 없습니다.

## 2. 정리 (같은 날)

```bash
bash deploy/teardown.sh   # 앱과 ALB를 먼저 지운다 — 남으면 비용이 계속 나고 VPC가 안 지워진다
terraform -chdir=infra/terraform/eks destroy -var aws_profile=team-admin -var 'admin_principal_arns=["arn:aws:iam::431777499129:user/<팀원>"]'
```

그 뒤 EC2 콘솔에서 로드밸런서·EBS 볼륨·네트워크 인터페이스가 남지 않았는지 확인하고, 팀에 알립니다.
`terraform plan`의 "No changes"는 리소스가 없다는 뜻이 아닙니다. 비용은 AWS Budgets로 봅니다 (Cost Explorer는 조직 정책으로 막혀 있음 — 매주 월요일 비용 메일, 바로 보기는 [docs/aws.md](../docs/aws.md#비용)).
최종 배포(`SCALING=1`)도 정리 순서는 같습니다 — KEDA·Cluster Autoscaler는 클러스터와 함께 지워지고 AWS에 남는 것이 없습니다.

정리 후 로컬 개발을 이어갈 때는 각자 동일 승인 코드·실제 모델 설정으로 `services/`에서 `bash scripts/dev.sh`를 실행합니다. API가 이미 실행 중이면 별도 터미널에서 `uv run ocr-worker`로 워커만 켭니다. 다른 워커가 남아 있으면 EKS를 꺼도 분석은 계속되고, 모든 워커가 꺼져 있으면 큐에 남은 요청은 워커가 다시 켜질 때 처리됩니다. 배포 코드·모델이 다르면 [공용 워커 전환 절차](../docs/worker.md#ocr공통-코드나-모델을-수정할-때)에 따라 버전을 맞춥니다.

## 자동 확장 (최종 배포)

- **HPA:** api·chat·preprocess, CPU 70% 기준 (`deploy/k8s/*.yaml`). `metrics-server` 애드온은 EKS 스택에 포함.
- **KEDA:** 분석 큐에 쌓인 메시지 5개당 ocr-worker 1개 (1~5개, `deploy/k8s-scaling/`). KEDA는 자기 역할(`keda-operator`)로 큐 길이만 읽습니다.
- **Cluster Autoscaler:** Pod가 노드에 안 들어가면 노드를 늘립니다. 2대로 시작해 최소 1·최대 3대 범위에서 조절합니다. 축소 대상이 5분간 유지돼야 하고, 확장 직후에는 기본 10분의 축소 보호 대기도 있어 바로 줄지 않습니다. 노드 그룹 크기는 Terraform이 되돌리지 않습니다.
- OCR 워커의 최소값이 1이므로 축소는 KEDA의 `cooldownPeriod`가 아닌 HPA가 담당합니다. 현재 HPA 축소 안정화 시간은 120초입니다.
- 권한: `infra/terraform/admin/scaling.tf` (역할), 연결: `infra/terraform/eks` (Pod Identity). 역할은 클러스터가 없을 때 비용이 없습니다.
- 자동 확장 시연에서는 로컬 워커가 큐를 함께 소비하면 EKS 부하가 줄어들 수 있으므로 로컬 워커를 잠시 종료합니다. 실제 Bedrock 비용이 드는 무분별한 부하 생성은 피하고, 부하 검사는 별도 mock 환경에서 진행합니다.
- 시연: `kubectl -n receipt-flow get hpa,scaledobject,pods -w`와 `kubectl get nodes -w`를 띄워 두고 영수증을 여러 장 올리면 ocr-worker와 노드가 늘어나는 것을 볼 수 있습니다.
