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

설치부터 실행까지는 **[로컬 개발 시작하기](docs/local-setup.md)** 하나만 순서대로 따라가면 됩니다(Windows·Mac). 도구 설치 → 저장소 받기 → AWS 로그인 → 환경 파일 → 설치 확인 테스트 → 서버 실행 → 웹 로그인 → 작업을 PR로 올리기까지 들어 있습니다. 명령은 그 문서에만 두고 여기에는 반복하지 않습니다.

알아 둘 것:
- 로컬 서버도 팀 **공용 DynamoDB·S3·SQS·Cognito·Bedrock**을 씁니다. PC에 DB를 설치하거나 EKS를 만들 필요가 없습니다. `.env`나 AWS 인증정보는 팀원끼리 복사하지 않고 각자 만듭니다.
- 로컬에서 켜는 OCR 워커는 공용 큐의 모든 팀원 사진을 처리합니다. 켜도 되는 조건은 [OCR 워커 운영](docs/worker.md)에 있습니다.
- 로컬 테스트는 로그인 화면의 "개발자 모드"로 합니다. Cognito 계정이 필요하면 개발자 모드 관리자 화면에서 직접 만들고 지워도 되며, 다른 사람이 만든 계정은 지우지 않습니다(local-setup.md 6단계).
- Cognito 없이 역할 선택 로그인만 볼 때: `RF_AUTH_MODE=dev bash scripts/dev.sh` + `npm run dev:devauth` (http://localhost:5180).
- 컨테이너로 배포와 같은 구성을 띄울 때: `bash deploy/local/run.sh` → http://localhost:8088 (로컬 서버와 동시에 켜지 않기, [deploy/README.md](deploy/README.md)).

## 테스트

PR 전 검사 명령은 [AGENTS.md](AGENTS.md#브랜치pr검사)에 있습니다. 백엔드 테스트는 moto로 AWS를 흉내 내므로 계정·비용이 필요 없습니다.

## AWS 리소스와 비용

| 스택 | 내용 | 비용 | 적용 |
|---|---|---|---|
| `infra/terraform/base` | S3, SQS(+DLQ), DynamoDB, Cognito, ECR | 사용량만큼 (거의 0) | 생성됨 |
| `infra/terraform/admin` | 서비스별 IAM 정책·Pod Identity 역할, EKS 역할, 이미지 90일 자동 삭제, GitHub OIDC | 무료 | IAM 관리자(박준영·장차희)만 — IAM 변경은 금지 정책으로 막혀 있음 |
| `infra/terraform/eks` | VPC(NAT 없음), EKS t3.medium — 테스트 1대 / 최종 2~3대(자동 확장), CloudFront HTTPS(`edge`) | 약 $0.20/h + ALB | **2026-10-30부터 노드 1대로 켜져 있음** (https://d287ue1u7s8yrk.cloudfront.net), 데모 전날 최종 방식으로 전환 |

영수증 사진은 S3에서 90일 뒤 자동 삭제됩니다. 배포 절차: [deploy/README.md](deploy/README.md). Bedrock 모델(영수증 분석 Sonnet 5.5, 챗봇 Haiku 5.5)과 평가 수치: [docs/model-eval.md](docs/model-eval.md).

## 구현 상태

기능별 상태·검증 범위·남은 일은 [docs/architecture.md](docs/architecture.md#6-현재-구현-상태)에 있습니다.
