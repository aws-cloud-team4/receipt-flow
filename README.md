# receiptflow — 영수증 증빙 접수·검수 AI 서비스

직원이 업무용 카드 영수증을 찍어 올리면 AI(Bedrock)가 증빙 정보를 읽고, AI 어시스턴트가 결과 확인 → 지출 목적·분류 추천 → 최종 확인까지 함께 진행합니다. 검수 담당자는 검토 포인트를 보며 먼저 제출된 순서대로 승인하거나 보완을 요청하고, 월별 CSV로 내보냅니다.
**처음이면 이 순서로 읽으세요:** [AGENTS.md](AGENTS.md)(개발 지침) → [docs/architecture.md](docs/architecture.md)(전체 구조·현재 상태·남은 일) → 자기 영역 문서
([ui.md](docs/ui.md) 웹 · [ai.md](docs/ai.md) AI · [backend.md](docs/backend.md) 백엔드 · [aws.md](docs/aws.md) AWS·배포) · 서비스 규약 [contract.md](docs/contract.md) · 기획서·발표자료 [docs/planning/](docs/planning/)

```
브라우저 ──PUT──▶ S3 raw/{id}.jpg (원본) ─▶ preprocess-service: 테두리 찾기 → 사용자 확인 → 자르기
                                                        └─▶ S3 incoming/{id}.jpg ──이벤트──▶ SQS ──▶ ocr-worker ──▶ Bedrock
   ├─ /api        ▶ api-service   (증빙 CRUD·제출·검수·CSV)        ┐
   ├─ /chat       ▶ chat-service  (AI 어시스턴트, SSE 스트리밍)    ├─▶ DynamoDB (단일 테이블)
   └─ /preprocess ▶ preprocess-service                              ┘
로그인: Cognito (직원 employee / 검수 담당자 reviewer / 관리자 admin 그룹)
```

| 폴더 | 내용 | 주 담당 |
|---|---|---|
| `web/` | React 웹 (직원·검수 담당자·관리자 화면, 촬영·업로드, AI 어시스턴트) | ① 장차희 |
| `services/ocr-worker`, `services/chat-service`, `services/preprocess-service` | 추출 프롬프트·스키마, 대화 정리, 이미지 보정 | ② 김태희 |
| `services/api-service`, `services/common` | API, DynamoDB, 권한, 상태 전환 | ③ 김수빈 |
| `infra/terraform`, `deploy/`, `.github/workflows` | AWS 리소스, EKS, CI/CD | ④ 박준영 |

## 로컬에서 실행 (실제 AWS 리소스 사용)

**처음 설치하는 팀원:** [로컬 개발 시작하기](docs/local-setup.md)를 순서대로 따라가세요. 도구 설치·저장소 받기·AWS 로그인·환경 파일·터미널별 실행·웹 로그인·종료·오류 해결까지 정리했습니다. 아래는 빠른 실행 요약입니다.

필요: Python 3.13 + [uv](https://docs.astral.sh/uv/), Node 22+, 본인 IAM 사용자로 AWS CLI `team-admin` 프로필 로그인 (팀 공통 프로필 이름, 루트 계정 금지).

Windows에서는 아래 실행 명령을 **Git Bash**에서 실행합니다. 저장소를 받은 각 팀원은 본인 AWS 로그인 후 환경 파일을 생성합니다. `.env`나 AWS 인증정보를 팀원끼리 복사하지 않습니다. AWS 로그인 방법은 [docs/aws.md](docs/aws.md#처음-설정-팀원)를 참고하세요.

설정 파일 만들기 — 본인 AWS 로그인으로 공유 리소스를 조회만 해서 `services/.env`, `web/.env.local`을 씁니다 (AWS는 바꾸지 않음, 있는 파일은 `--force` 없이는 그대로):

```bash
(cd services && uv run python scripts/make_env.py --dev-login)
```

Terraform 상태가 있는 사람은 `terraform -chdir=infra/terraform/base output -raw services_env`로도 같은 값을 얻습니다.

```bash
cd services && uv sync --frozen && bash scripts/dev.sh
```

```bash
cd web && npm install && npm run dev
```

위 두 명령은 프로젝트 루트에서 **서로 다른 터미널**로 각자 실행합니다. `dev.sh`는 API·chat·preprocess와 OCR 워커를 함께 켭니다. 워커는 공용 큐의 모든 팀원 사진을 처리하므로 켜도 되는 조건(최신 `main` 코드·실제 Bedrock 설정)과 끄는 경우(`WORKER=0`), 분석이 대기할 때의 점검은 [OCR 워커 운영](docs/worker.md)에 있습니다.

로컬 서버도 **공용 DynamoDB·S3·SQS·Cognito**를 사용합니다. 별도 로컬 DB 설치나 EKS 생성은 필요하지 않습니다. 공용 데이터를 바꾸지 않는 검증은 아래 moto 기반 테스트를 사용합니다.

http://localhost:5173 에서 로그인합니다. 계정은 관리자가 관리 화면에서 만들고(임시 비밀번호 한 번 표시), 사용자는 첫 로그인 때 새 비밀번호를 정합니다. 최초 관리자 준비는 팀 관리자만 수행합니다. 일반 팀원은 계정 발급을 요청하며 `seed_users.py`를 실행하지 않습니다.

비밀번호 없이 화면만 볼 때:
- **개발자 로그인:** `services/.env`에 `RF_DEV_LOGIN=true` → 로그인 화면 아래 "개발자 모드"에서 테스트 계정 10개(직원 7·검수 2·관리자 1) 중 선택. 샘플 생성·일괄 정리는 팀 사전 공유 후 담당자가 수행합니다. `clear_dev_data.py`는 본인이 넣은 샘플만이 아니라 **모든 공용 개발 계정(`dev-*`)의 증빙·대화·이력·사진을 삭제**하므로 일반 실행 절차에서 사용하지 않습니다
- Cognito 없이: `RF_AUTH_MODE=dev bash scripts/dev.sh` + `npm run dev:devauth` (http://localhost:5180)

AI 호출 없이 테스트할 때는 아래 자동 테스트(moto + `RF_AI_MODE=mock`)를 씁니다. mock 워커를 공용 큐에 연결하지 않습니다.
컨테이너로 한 번에 실행(배포와 같은 구성): `bash deploy/local/run.sh` → http://localhost:8088 (위 서버들과 동시에 켜지 않기).

## 테스트

```bash
cd services && uv run ruff format --check . && uv run ruff check . && uv run pytest
```

```bash
cd web && node --test tests/*.test.mjs && npm run build
```

백엔드 테스트는 moto로 AWS를 흉내 내므로 계정·비용이 필요 없습니다.

## AWS 리소스와 비용

| 스택 | 내용 | 비용 | 적용 |
|---|---|---|---|
| `infra/terraform/base` | S3, SQS(+DLQ), DynamoDB, Cognito, ECR | 사용량만큼 (거의 0) | 생성됨 |
| `infra/terraform/admin` | 서비스별 IAM 정책·Pod Identity 역할, EKS 역할, 이미지 90일 자동 삭제, GitHub OIDC | 무료 | IAM 관리자(박준영·장차희)만 — IAM 변경은 금지 정책으로 막혀 있음 |
| `infra/terraform/eks` | VPC(NAT 없음), EKS t3.medium — 테스트 1대 / 최종 2~3대(자동 확장), CloudFront HTTPS(`edge`) | 약 $0.20/h + ALB | 통합·데모 주간에만 |

영수증 사진은 S3에서 90일 뒤 자동 삭제됩니다. 배포 절차: [deploy/README.md](deploy/README.md). Bedrock 모델: 영수증 분석 `RF_EXTRACT_MODEL=global.anthropic.claude-sonnet-5-5` (측정 조건별 지연·비용은 평가 문서 참고), 챗봇 답변 정리 `RF_CHAT_MODEL=global.anthropic.claude-haiku-5-5`. 현재 모델·평가 수치: [docs/model-eval.md](docs/model-eval.md).

## 구현 상태

기능별 상태·검증 범위·남은 일은 [docs/architecture.md](docs/architecture.md#6-현재-구현-상태)에 있습니다.
