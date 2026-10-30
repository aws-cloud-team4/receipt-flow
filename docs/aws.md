# AWS·배포 — ④ 박준영

계정 `431777499129`, 리전 서울 `ap-northeast-2`. 예산 $200, 2026-11-14까지. **리소스는 Terraform으로만** 만들고, **EKS는 2026-10-30부터 노드 1대로 계속 켜 둡니다**(하루 약 $5, 데모 전날 최종 방식으로 전환 — [deploy/README.md](../deploy/README.md#노드-1개로-먼저-띄우고-나중에-최종-배포로-바꾸기)).
명령 순서만 필요하면 [deploy/README.md](../deploy/README.md).

## 처음 설정 (팀원)

1. **IAM 사용자**: 팀원 4명(chahee·junyoung·subin·taehee)의 IAM 사용자는 이미 있습니다. 콘솔 로그인 비밀번호는 IAM 관리자(박준영·장차희)에게 받고, 첫 로그인 때 바꾸고 **MFA를 켭니다**. 루트 계정은 쓰지 않습니다.
2. **CLI 로그인·환경 파일**: 프로필 이름은 팀 공통 **`team-admin`**, 로그인하는 사람은 각자 본인. 명령은 [로컬 개발 시작하기](local-setup.md#3-처음-한-번-및-세션-만료-시-aws-로그인) 3·4단계.
3. 배포하는 사람만: docker, kubectl, helm(`winget install Helm.Helm`, PATH 확인).

## 스택 6개 (`infra/terraform/`)

상태 파일은 전부 S3 `receipt-flow-tfstate-431777499129/<스택>/terraform.tfstate`(버전 관리, S3 기본 잠금). 누구든 `terraform init` 후 같은 상태로 plan·apply 합니다 (같은 스택을 동시에 돌리면 잠금이 막음).

| 스택 | 만드는 것 | 비용 | 언제 apply |
|---|---|---|---|
| `state` | 상태 버킷 (이 스택의 상태만 로컬 파일 — 버킷은 다시 건드릴 일이 없고, 파일을 잃어도 버킷·다른 스택 상태는 그대로) | ~0 | 처음 한 번 |
| `base` | S3 `receipt-flow-dev-receipts-<계정>`(raw/·incoming/, CORS), SQS `receipt-flow-dev-analysis`(+DLQ, 3회 후), DynamoDB `receipt-flow-dev`(GSI 2), Cognito 사용자 풀·웹 클라이언트·그룹 3개, ECR 저장소 5개 | 사용량만큼 (~0) | 코드가 바뀌었을 때 |
| `admin` | 서비스별 IAM 정책·Pod Identity 역할, EKS 클러스터·노드 역할, ALB 컨트롤러 역할, 오토스케일러 역할(CA·KEDA), S3 사진 90일 삭제 규칙, GitHub OIDC 배포 역할(기본값 팀 저장소), **팀 금지 정책** | 0 | 권한이 바뀔 때 (IAM 관리자만) |
| `eks` | VPC(공인 서브넷 2, NAT 없음), EKS 1.35, 관리형 노드 그룹 t3.medium(최소 `node_min_count`(기본 1, 최종 2)·최대 3), 애드온(vpc-cni·coredns·kube-proxy·pod-identity-agent·metrics-server), Pod Identity 연결, 접근 권한 | **약 $0.20/h** | 켜져 있음 (노드 수 바꿀 때) |
| `edge` | CloudFront(`*.cloudfront.net` HTTPS) → ALB | 쉬는 동안 0 | `deploy.sh`가 자동 |
| `ops` | 예산 알림, 매주 월요일 비용 메일(Lambda·EventBridge·SNS), SSM 값 | ~0 | 받는 사람이 바뀔 때 |

```bash
terraform -chdir=infra/terraform/<스택> init
terraform -chdir=infra/terraform/<스택> plan  -var aws_profile=team-admin     # admin·eks는 aws_profile 필요
```
`ops`는 받는 메일이 필수 변수입니다 — 개인정보라 git에 없고 `infra/terraform/ops/terraform.tfvars`(git 제외)에 `report_emails = ["…"]`.

## 서비스가 갖는 권한 (최소 권한, `admin/iam.tf`)

| 서비스 | 권한 |
|---|---|
| api-service | 테이블 읽기·쓰기·삭제, 버킷 객체 읽기·쓰기·삭제(업로드 URL·사진 URL·삭제), Cognito 계정 관리(관리자 화면), 예산 읽기(소개 페이지 비용 카드) |
| chat-service | 테이블 읽기·쓰기, Bedrock 호출 |
| preprocess-service | 테이블 읽기·쓰기, `raw/`·`incoming/` 읽기·쓰기 |
| ocr-worker | 테이블 읽기·쓰기, `incoming/` 읽기, 분석 큐 받기·지우기, Bedrock 호출 |
| aws-load-balancer-controller, cluster-autoscaler, keda-operator | 각자 필요한 것만 (ALB 관리 / 이 클러스터 노드 그룹 크기 / 큐 길이 읽기) |

EKS에서는 **Pod Identity**(서비스 계정 ↔ IAM 역할)로 키 없이 권한을 받습니다. 새 권한이 필요하면 이 파일에 추가하고 PR.

## 팀 IAM 사용자와 금지 정책 (`admin/guard.tf`)

팀원 4명(chahee·junyoung·subin·taehee)은 `AdministratorAccess` + 거부 정책. **CLI·로컬 개발·배포는 그대로** 되고 다음은 금지 정책으로 막힙니다:

| 막는 것 | 누구 |
|---|---|
| 공유 리소스 삭제: 테이블, 버킷(삭제·정책 삭제), 큐(삭제·비우기), 사용자 풀·클라이언트·그룹·도메인, ECR 저장소 (`receipt-flow-*`), 상태 버킷 버전·수명 주기 변경 | 모두 |
| 서울 밖에 비용 드는 리소스 생성, `t3`/`t3a`/`t4g` 외 인스턴스, SageMaker | 모두 |
| IAM 사용자·역할·정책 변경, 다른 사람의 콘솔 비밀번호·액세스 키 변경 | junyoung·chahee 외 (`iam_admins`) |

정말 공유 리소스를 지워야 하면: 팀에 알림 → **IAM 관리자가** `terraform -chdir=infra/terraform/admin apply -var aws_profile=team-admin -var guard_enabled=false` → 작업 → 같은 날 `true`로 되돌림. 다른 팀원은 IAM 변경이 막혀 있어 `admin` 스택을 apply 할 수 없습니다 (IAM 관리자에게 요청). 루트 계정(프로필 `team-infra`)은 CLI·Terraform에 쓰지 않습니다.

## 배포 (EKS)

배포 방식(테스트 1대 / 최종 2~3대 + 자동 확장), 명령 순서, 1대→최종 전환은 [deploy/README.md](../deploy/README.md)에 있습니다. 여기는 구성·버전만 둡니다.

기본 Kubernetes 버전은 **1.35**이며 표준 지원 종료는 **2027-03-27**입니다. 제어 영역 요금은 표준 지원 **$0.10/h**, 연장 지원 **$0.60/h**이고 EC2·ALB·공인 IPv4 등은 별도입니다. 약 $0.20/h 추정은 표준 지원 버전·노드 1대 기준입니다. [공식 요금](https://aws.amazon.com/eks/pricing/)

배포 전에 지원 상태를 확인합니다:

```bash
aws eks describe-cluster-versions --region ap-northeast-2 --profile team-admin --cluster-versions 1.35
```

### 배포 구성

| 항목 | 현재 설정 |
|---|---|
| 기본 애드온 | `vpc-cni`, `coredns`, `kube-proxy`, `eks-pod-identity-agent`, `metrics-server` 사용. Terraform은 AWS가 제공하는 1.35 호환 기본 버전을 선택 |
| ALB Controller | 차트 **3.6.0** / 이미지 **v3.6.0** 고정. 저장소 IAM 정책은 해당 공식 버전 정책을 사용 |
| KEDA | 차트·이미지 **2.21.0** 고정. 공식 테스트 범위 Kubernetes **1.34~1.36**에 1.35 포함 |
| Cluster Autoscaler | 차트 **9.59.0**, 이미지 **v1.35.2** 고정. EKS와 같은 minor 버전, linux/amd64 이미지 사용 |
| kubectl | EKS 1.35에서 **1.34~1.36** 허용. 배포 스크립트가 실행 PC의 버전을 검사 |
| Pod Identity | Terraform과 연결하는 서비스 계정: `kube-system/aws-load-balancer-controller`, `kube-system/cluster-autoscaler`, `keda/keda-operator` |

버전은 **`deploy/versions.sh`** 한 곳에서 관리하고 `deploy.sh`가 읽습니다. 실제 EKS가 1.35가 아니거나 kubectl이 허용 범위를 벗어나면 Helm 설치 전에 중단합니다. 버전을 바꿀 때는 Terraform 기본값과 이 파일을 함께 검토합니다. Helm 차트의 최신 버전을 무조건 설치하지 않습니다.

KEDA는 `provider: aws`, `identityOwner: keda`로 운영자 자신의 자격 증명을 사용합니다. AWS SDK 기본 자격 증명 경로와 Pod Identity 연결을 사용하며 별도 IRSA 설정은 필요하지 않습니다. 관리형 노드 그룹의 자동 발견 태그는 EKS가 붙이고, Autoscaler 정책은 해당 클러스터 태그가 있는 그룹만 크기를 변경하도록 제한합니다.

근거: [KEDA 호환표](https://keda.sh/docs/2.21/operate/cluster/), [kubectl 버전 정책](https://kubernetes.io/releases/version-skew-policy/), [Autoscaler 버전 정책](https://github.com/kubernetes/autoscaler/blob/master/cluster-autoscaler/README.md), [ALB 설치 가이드](https://kubernetes-sigs.github.io/aws-load-balancer-controller/latest/deploy/installation/), [관리형 노드 그룹 자동 발견](https://docs.aws.amazon.com/eks/latest/userguide/managed-node-groups.html).

- `deploy.sh` 순서: kubeconfig → AWS Load Balancer Controller(Helm) → (최종) KEDA·Cluster Autoscaler → 이미지 5개 빌드·ECR 업로드(태그 = 커밋) → `kubectl apply -k deploy/k8s` (+ `deploy/k8s-scaling`) → ALB 주소 대기 → CloudFront를 새 ALB로 → **https 주소 출력**. 다시 실행해도 됩니다(제자리 갱신).
- 매니페스트: `deploy/k8s/` (kustomize). 설정은 `config.yaml`(ConfigMap, 비밀값 없음 — 권한은 Pod Identity), 서비스마다 Deployment·Service·(HPA), `ingress.yaml`(ALB 하나, `/api` `/chat` `/preprocess` `/`).
- **개발자 로그인은 배포 설정에 없음** → 배포에서는 꺼져 있음 (`/api/dev/profiles` 404). CI `manifests` 검사가 확인합니다.
- 로컬·EKS 워커는 같은 공용 큐를 소비합니다 — 분석 코드·모델 버전 맞추기는 [worker.md](worker.md).

### CI·자동 배포 (`.github/workflows/`)

- `ci.yml` — PR 필수 검사 5종: **services**(ruff format·check, pytest), **web**(검수 정렬·분석 시간·보완 사유 회귀 검사 + build), **terraform**(fmt, 스택 6개 validate), **images**(배포 이미지 5개 빌드 — 서비스 4개 + 웹(Cognito 기본값), 이미지마다 따로 돌아 GitHub에는 `images (api-service)` 등 5개로 표시), **manifests**(`deploy/k8s` kustomize 렌더링 → kubeconform 스키마 검사(KEDA 객체는 형식만), 배포 설정이 `RF_AUTH_MODE: cognito`·`RF_AI_MODE: bedrock`이고 `RF_DEV_LOGIN`이 없는지 확인). 그래서 `main` 보호의 필수 체크는 9개입니다.
- `deploy.yml` — `main` 머지(서비스·웹·매니페스트 변경) 또는 수동 실행 → **클러스터가 켜져 있으면** 이미지 빌드·ECR → 롤아웃, 없으면 건너뜀. 배포 역할(`admin` 스택 `github.tf`)·Secret `AWS_DEPLOY_ROLE_ARN`·클러스터 접근 권한은 설정돼 있습니다 — 주의할 점은 [deploy/README.md](../deploy/README.md#1-배포).

## 비용

- **Cost Explorer는 쓸 수 없습니다.** 이 계정은 부트캠프 AWS Organization 안에 있고 조직 정책(SCP)이 `ce:*` 조회를 막습니다 (콘솔 "비용 및 사용량"도 "액세스 거부됨").
- 대신 **AWS Budgets**를 씁니다 (`ops` 스택, 예산 2개):
  - **"aws-team4-receipt-flow"** — 이 프로젝트, 2026-10-01 ~ 2026-11-14 (사용자 지정 기간). 실제 $50·$100·$150 초과, 예측이 $200 초과 시 메일. 주간 메일도 이것만 씀
  - **"aws-team4"** — 계정 전체 올해(1월부터, 팀 이전 사용 포함). 참고용, 알림 없음
  - **예산 이름을 바꾸지 마세요.** 콘솔에서 만든 "예산 보고서"(매주 두 예산을 메일로, API 없음 — 콘솔에서만 생성)가 이 이름을 가리키고, Terraform에서 이름을 바꾸면 예산이 새로 만들어져 보고서가 사라집니다.
- **매주 월요일 09:00(KST) 비용 메일**: **10월부터 누적**(예산 $200 대비 남은 금액, 지난 보고 대비 증가)과 **지금 켜져 있는 시간당 과금 리소스**(EKS·EC2·LB·NAT·연결 안 된 EIP). 받는 사람은 SNS 구독 확인 메일의 링크를 한 번 눌러야 시작. 바로 보내 보기: `aws lambda invoke --function-name receipt-flow-dev-cost-report --profile team-admin --region ap-northeast-2 out.json`
- 프로젝트 예산은 **2026-10-01부터** 집계합니다. 계정 전체 누적과 구분하고 현재 금액은 아래 API 또는 비용 카드에서 조회합니다. Budgets는 지연 집계이므로 즉시 발생한 비용이 모두 반영되지는 않습니다.
- 콘솔의 결제·예산 화면은 IAM 사용자에게 막혀 있습니다(루트가 "결제 정보에 대한 IAM 액세스"를 켜야 하고, 조직 정책으로 계속 막힐 수 있음). 명령어로 보기: `aws budgets describe-budget --account-id 431777499129 --budget-name aws-team4-receipt-flow --profile team-admin --region us-east-1 --query Budget.CalculatedSpend`
- EKS 비용 추정은 위 배포 구성을 기준으로 합니다. AI 비용은 [모델 평가 문서](model-eval.md)의 측정 조건별 추정치를 참고하고, 실제 청구는 Budgets에서 확인합니다.

## 문제 해결

| 증상 | 원인 | 현재 처리·해결 방법 |
|---|---|---|
| `eks apply`: access entry already in use | 클러스터 만든 사람은 자동으로 관리자 → `admin_principal_arns`에 또 넣으면 충돌 | 만드는 사람은 자동 제외 |
| `docker login`: The stub received bad data | Windows 자격 증명 저장소가 긴 ECR 토큰 거부 | `deploy.sh`가 임시 Docker 설정 + 도우미 없는 PATH로 docker 실행 |
| Docker 시작 시 `initializing Inference manager … dockerInference` 또는 `initializing Secrets Engine … engine.sock` + `The file cannot be accessed by the system` | 이전 실행의 임시 소켓 파일이 남아 엔진 시작 실패(앱 창이 떠 있어도 엔진은 안 돎). 강제 종료하면 다음 시작 때 다시 생길 수 있음 | Docker를 완전히 종료 → `%LOCALAPPDATA%\Docker\run`과 `%LOCALAPPDATA%\docker-secrets-engine`을 **둘 다** 백업 이름으로 옮기고 재시작(파일 하나만은 옮겨지지 않음). 컨테이너·이미지·볼륨·설정은 지우지 않음. `docker info` 응답으로 확인. `deploy.sh`는 엔진 확인을 20초로 제한 |
| `kubectl apply`: x509 certificate signed by unknown authority (webhook) | ALB 컨트롤러를 다시 설치하면 웹훅 인증서가 바뀜 | `keepTLSSecret=true` + 설치 후 컨트롤러 재시작 |
| `aws`: Your session has expired | `aws login` 세션 만료 | `aws login --profile team-admin` (브라우저에서 마지막 허용까지) |
| Helm이 "명령을 찾을 수 없음" | winget 설치 후 PATH 미등록 | 사용자 PATH에 Helm 폴더 추가 후 새 터미널 |
