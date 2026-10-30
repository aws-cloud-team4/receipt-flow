# EKS 배포 절차

구성·버전·권한·비용·문제 해결은 [docs/aws.md](../docs/aws.md). 이 문서는 명령 순서입니다.

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

## 1. 배포

팀 합의 후 만듭니다. EKS는 시간당 비용(약 $0.20/h, 노드 1대 기준)이 나므로 **같은 날** 지우는 것이 원칙입니다(예외: 2026-10-30부터 데모까지 노드 1대로 켜 둠 — 아래 "노드 1개로 먼저 띄우고…"). Kubernetes **1.35**, 도구 버전은 `deploy/versions.sh`에 고정돼 있고 `deploy.sh`가 클러스터·kubectl 버전을 먼저 검사합니다 — 버전을 올리기 전에 [배포 구성](../docs/aws.md#배포-구성)을 확인하세요.

두 가지 방식이 있습니다:

| | 테스트·리허설 | 최종 배포 (발표) |
|---|---|---|
| 노드 | 1대 (`node_count=1`, 기본) | 2~3대: 최소 2·최대 3 (`-var node_count=2 -var node_min_count=2`) |
| 자동 확장 | 없음 (HPA만, 부하가 없으면 그대로) | Cluster Autoscaler(노드) + KEDA(큐 길이 → ocr-worker 1~5개) + HPA(api·chat·preprocess) |
| 배포 명령 | `bash deploy/deploy.sh` | `SCALING=1 bash deploy/deploy.sh` |
| 비용 | 약 $0.20/h | 약 $0.25~0.30/h |
필요한 도구: `aws`(프로필 `team-admin` = 본인 IAM 사용자, 루트 금지), `docker`, `kubectl`, `helm`(`winget install Helm.Helm`).

| 단계 | 명령 |
|---|---|
| 1. 기본 리소스 (S3·SQS·DynamoDB·Cognito·ECR) — 이미 있음, 코드가 바뀌었으면 | `terraform -chdir=infra/terraform/base apply` |
| 2. IAM 역할·정책 — 코드가 바뀌었으면 | `terraform -chdir=infra/terraform/admin apply -var aws_profile=team-admin` |
| 3. EKS 클러스터 (약 15분) — 최종 배포는 `-var node_count=2 -var node_min_count=2` 추가 | `terraform -chdir=infra/terraform/eks apply -var aws_profile=team-admin -var 'admin_principal_arns=["arn:aws:iam::431777499129:user/<팀원>"]'` |
| 4. 연결·ALB 컨트롤러·(최종: 자동 확장 설치)·이미지 빌드/업로드·배포·HTTPS 연결·주소 출력 | `bash deploy/deploy.sh` (최종: `SCALING=1 bash deploy/deploy.sh`) |

`deploy.sh`는 다시 실행해도 됩니다 (현재 커밋으로 이미지를 다시 올리고 갱신).

**HTTPS:** `deploy.sh` 마지막에 CloudFront(`infra/terraform/edge`)가 새 ALB를 가리키게 바꾸고 **`https://….cloudfront.net` 주소**를 출력합니다. 휴대폰 카메라는 HTTPS에서만 동작하므로 이 주소로 접속합니다(`http://<ALB 주소>`는 확인용). 도메인이 필요 없고 무료 범위입니다. CloudFront는 정리 때 지우지 않아 다음 배포에도 **같은 주소**를 씁니다(클러스터가 없을 때는 502). S3 업로드 허용 주소에 ALB·CloudFront 주소 패턴이 들어 있어 따로 고칠 것이 없습니다.

**자동 배포 (GitHub Actions `deploy`):** 클러스터가 켜져 있는 동안 `main`에 서비스·웹·매니페스트 변경이 머지되면 새 이미지로 롤아웃합니다(클러스터가 없으면 건너뜀). 수동 실행은 Actions → deploy → Run workflow. **팀 저장소는 설정이 끝나 있습니다**(배포 역할 `receipt-flow-dev-github-deploy`, Secret `AWS_DEPLOY_ROLE_ARN`).

- 클러스터를 새로 만들면 `deploy.sh`를 먼저 한 번 실행합니다. ALB 컨트롤러·자동 확장·HTTPS는 Actions가 설치하지 않습니다.
- 배포 역할의 클러스터 접근 권한은 `eks` 스택이 `admin` 출력에서 읽어 **자동으로** 넣습니다(`admin_principal_arns`에 적지 않음).
- `admin` 스택의 `github_repo`·`github_sub_prefix` 기본값이 팀 저장소입니다. `-var github_repo=""`로 apply하면 배포 역할이 지워집니다.
- 역할은 `demo` 환경과 `main`에서만 받을 수 있습니다. 팀 저장소는 GitHub의 고정 subject(ID가 붙은 `sub`)를 쓰므로 신뢰 조건에 두 형식을 모두 넣었습니다.
- CloudFront는 바꾸지 않습니다(ALB가 그대로라 주소도 그대로).

### 노드 1개로 먼저 띄우고 나중에 최종 배포로 바꾸기

지금 클러스터는 2026-10-30부터 테스트 방식(노드 1대, 최소 1)으로 켜져 있습니다. 데모 전날 지우지 않고 최종 방식(노드 **2~3대**, 자동 확장)으로 바꿉니다. 주소는 그대로입니다.

1. 노드 수를 먼저 2대로 (AWS는 노드 수보다 큰 최소값을 거부하므로 이 순서):
   ```bash
   aws eks update-nodegroup-config --cluster-name receipt-flow-dev --nodegroup-name default --scaling-config minSize=2,maxSize=3,desiredSize=2 --profile team-admin --region ap-northeast-2
   ```
   `terraform apply -var node_count=2`로는 노드 수가 바뀌지 않습니다. Cluster Autoscaler와 다투지 않도록 Terraform이 만든 뒤의 노드 수(`desired_size`)를 무시하기 때문입니다.
2. Terraform 코드도 최소 2로 맞춥니다 (안 하면 다음 `eks` apply가 최소를 1로 되돌림). `admin_principal_arns`를 빼면 팀원 접근 권한이 지워지므로 그대로 넣습니다. plan은 바뀌는 것이 없어야 합니다.
   ```bash
   terraform -chdir=infra/terraform/eks apply -var aws_profile=team-admin -var node_min_count=2 -var 'admin_principal_arns=["arn:aws:iam::431777499129:user/junyoung","arn:aws:iam::431777499129:user/subin","arn:aws:iam::431777499129:user/taehee"]'
   ```
3. `SCALING=1 bash deploy/deploy.sh` — KEDA·Cluster Autoscaler를 설치하고 같은 ALB·CloudFront 주소로 갱신합니다.
4. 확인: `kubectl get nodes`(2대), `kubectl -n receipt-flow get hpa,scaledobject`. 부하가 오면 3대까지 늘고, 끝나면 2대로 돌아옵니다(1대로는 줄지 않음).
5. 시연 후: 같은 날 정리(아래 2절)하거나, 계속 켜 둘 거면 1번을 `minSize=1,maxSize=3,desiredSize=1`, 2번을 `-var node_min_count=1`로 되돌립니다.

여러 날 켜 두면 하루 약 $5(노드 1대, ALB 포함 추정)가 계속 나갑니다. 켜 둔 기간과 이유를 팀에 알리고, 월요일 비용 메일의 "켜져 있는 시간당 과금 리소스"로 확인합니다.

## 2. 정리 (같은 날)

```bash
bash deploy/teardown.sh   # 앱과 ALB를 먼저 지운다 — 남으면 비용이 계속 나고 VPC가 안 지워진다
terraform -chdir=infra/terraform/eks destroy -var aws_profile=team-admin -var 'admin_principal_arns=["arn:aws:iam::431777499129:user/<팀원>"]'
```

그 뒤 남은 것(EKS·EC2·LB·NAT·EIP·EBS·ENI·VPC·대상 그룹)이 없는지 확인하고 팀에 알립니다. 최종 배포(`SCALING=1`)도 순서는 같습니다 — KEDA·Cluster Autoscaler는 클러스터와 함께 지워집니다. 비용 확인은 [docs/aws.md](../docs/aws.md#비용).

EKS를 지우면 EKS의 ocr-worker도 없어지므로, 분석은 로컬 워커가 맡습니다([worker.md](../docs/worker.md)).

## 자동 확장 (최종 배포)

- **HPA:** api·chat·preprocess, CPU 70% 기준 (`deploy/k8s/*.yaml`). `metrics-server` 애드온은 EKS 스택에 포함.
- **KEDA:** 분석 큐에 쌓인 메시지 5개당 ocr-worker 1개 (1~5개, `deploy/k8s-scaling/`). KEDA는 자기 역할(`keda-operator`)로 큐 길이만 읽습니다.
- **Cluster Autoscaler:** Pod가 노드에 안 들어가면 노드를 늘립니다. 최종 배포는 최소 2·최대 3대 범위에서 조절합니다(`node_min_count=2`). 축소 대상이 5분간 유지돼야 하고, 확장 직후에는 기본 10분의 축소 보호 대기도 있어 바로 줄지 않습니다. 노드 수는 Terraform이 되돌리지 않지만 최소값(`node_min_count`)은 Terraform이 관리합니다.
- OCR 워커의 최소값이 1이므로 축소는 KEDA의 `cooldownPeriod`가 아닌 HPA가 담당합니다. 현재 HPA 축소 안정화 시간은 120초입니다.
- 권한: `infra/terraform/admin/scaling.tf` (역할), 연결: `infra/terraform/eks` (Pod Identity). 역할은 클러스터가 없을 때 비용이 없습니다.
- 자동 확장 시연에서는 로컬 워커가 큐를 함께 소비하면 EKS 부하가 줄어들 수 있으므로 로컬 워커를 잠시 종료합니다. 실제 Bedrock 비용이 드는 무분별한 부하 생성은 피하고, 부하 검사는 별도 mock 환경에서 진행합니다.
- 시연: `kubectl -n receipt-flow get hpa,scaledobject,pods -w`와 `kubectl get nodes -w`를 띄워 두고 영수증을 여러 장 올리면 ocr-worker와 노드가 늘어나는 것을 볼 수 있습니다.
