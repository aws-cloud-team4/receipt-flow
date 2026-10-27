# 백엔드·DB — ③ 김수빈 (서비스 공통 구조는 모두)

`services/`는 uv 워크스페이스입니다. Python 3.13, FastAPI, boto3. 서비스 4개가 공통 패키지 하나(`receiptflow_common`)를 씁니다.
엔드포인트·필드·상태의 정확한 약속은 [contract.md](contract.md) — **이 문서는 내부 구조**입니다. AI 쪽 내부는 [ai.md](ai.md).

## 실행·검사

처음 설치부터 브라우저 접속까지는 [로컬 개발 시작하기](local-setup.md)를 따릅니다. 아래는 백엔드 명령 요약입니다.

```bash
cd services
uv sync                                   # 의존성 (워크스페이스 전체)
uv run python scripts/make_env.py --dev-login   # services/.env, web/.env.local 만들기 (본인 AWS 로그인으로 조회만)
bash scripts/dev.sh                       # api 8000 · chat 8001 · preprocess 8002 + OCR 워커 (실제 공유 AWS 사용)
uv run ruff format --check . && uv run ruff check . && uv run pytest   # CI 필수 검사 "services"
```

- `RF_AI_MODE=mock`: Bedrock 없이 고정 추출 + 대본 대화. moto 또는 별도 테스트 리소스에서 사용하며 공용 큐에 mock 워커를 연결하지 않습니다. `RF_AUTH_MODE=dev`: 개발 토큰만 받음(자동 테스트). `RF_DEV_LOGIN=true`: Cognito와 함께 개발 토큰도(로컬 화면 "개발자 모드").
- **공용 워커:** `dev.sh`가 켜는 OCR 워커는 공용 큐의 모든 팀원 사진을 처리합니다. 켜도 되는 조건, `WORKER=0`, 워커만 켜기는 [worker.md](worker.md).
- `dev.sh`는 `--reload` 없이 띄웁니다 (Windows에서 Ctrl+C 뒤 포트가 남는 문제). 코드를 바꾸면 다시 실행합니다.
- `analysis_status=queued`가 계속되면 [워커 점검](worker.md#분석이-대기하거나-실패할-때)대로 로그·AWS 세션·큐 설정을 확인합니다. 개발자 로그인은 서버의 AWS 접근 자격 증명을 대신하지 않습니다.

## 패키지 구조

| 패키지 | 진입점 | 하는 일 |
|---|---|---|
| `common/receiptflow_common` | — | 아래 모듈 |
| `api-service/api_service` | `main.py`(앱 조립), `routes/`(기능별 HTTP), `receipt_workflows.py`(증빙 업무 처리), `schemas.py`(요청 모델), `admin.py`·`dev.py`·`usage.py`(기존 라우터) | 증빙 CRUD·업로드 URL·제출·검수·CSV·메타, 관리자 계정·증빙 |
| `chat-service/chat_service` | `main.py` (`/chat/...`), `agent.py`, `dialog.py` | AI 어시스턴트 ([ai.md](ai.md)) |
| `preprocess-service/preprocess_service` | `main.py`, `correct.py` | 사진 테두리·보정 |
| `ocr-worker/ocr_worker` | `main.py` (`ocr-worker` 명령), `extractor.py` | SQS 소비·추출 |

`api_service/usage.py` — 공개 `GET /api/public/usage`: 09:00(KST) 기준 날짜 키의 캐시가 없으면 AWS Budgets(`RF_USAGE_BUDGET`)를 읽어 DynamoDB에 저장하고 이후 재사용합니다. 최초 동시 요청에는 중복 조회·저장이 가능하며 정확히 한 번 실행 보장은 없습니다. Budgets 클라이언트는 `aws.client("budgets")`(us-east-1).

### API 기능을 추가할 위치

| 파일 | 책임 |
|---|---|
| `api_service/main.py` | 앱 생성과 라우터 등록만 담당. 실행 진입점 `api_service.main:app` 유지 |
| `routes/metadata.py` | `/api/me`, `/api/meta` |
| `routes/receipts.py` | 증빙 생성·목록·조회·수정·삭제·재촬영·업로드 완료·제출의 HTTP 입구 |
| `routes/review.py` | 검수 목록·승인·보완 요청의 HTTP 입구와 검수자 인증 |
| `routes/exports.py` | 월별 CSV 응답 생성 |
| `receipt_workflows.py` | 소유권·수정 가능 여부 검사, 증빙 변경·제출·검수 상태 전환과 이력 기록 |
| `schemas.py` | `PatchReceipt`, `ChangeRequest` 요청 형식. HTTP와 업무 처리에서 함께 사용 |
| `admin.py`, `dev.py`, `usage.py` | 관리자·로컬 개발자 로그인·공개 비용 조회 기능 |

의존 방향은 **라우터 → 업무 처리 → 공통 저장소·도메인**입니다. 업무 처리에는 FastAPI `Depends`를 넣지 않고 인증된 사용자를 명시적으로 전달합니다. 역할 인증은 라우터가 담당하므로 업무 함수를 새 HTTP 입구에서 재사용할 때도 해당 인증 의존성을 붙입니다. DynamoDB 테이블·키·저장 방식은 그대로이며, 서비스들이 같은 저장 구조를 공유한다는 점도 변하지 않습니다.

새 기능은 기존 기능 라우터에 넣거나 새 라우터 파일을 만든 뒤 `main.py`에 등록합니다. 제출·검수 같은 업무 규칙은 라우터에 복사하지 않고 업무 처리 함수로 모읍니다. API·필드·상태가 바뀌면 먼저 `contract.md`를 고치고 웹 타입과 테스트를 함께 갱신합니다.

### 공통 모듈 상세 (`receiptflow_common`)

| 모듈 | 내용 |
|---|---|
| `config.py` | `Settings` — 모든 설정은 `RF_*` 환경 변수(`services/.env.example`). `.env`는 `RF_ENV_FILE`로 바꿀 수 있음(테스트는 없는 파일) |
| `webapp.py` | `create_app(title)`: CORS, 오류 처리기, `GET /healthz` |
| `errors.py` | `ApiError(status, code, message)` → `{"error": {code, message}}` |
| `aws.py` | **AWS 클라이언트는 반드시 여기서** (`client("s3")`, `table()`) — 테스트에서 moto로 바뀜. 로컬은 `AWS_PROFILE`, EKS는 Pod Identity |
| `auth.py` | `current_user` (Bearer 토큰 → `User`), `employee_only`, `reviewer_only`, `admin_only`. Cognito ID 토큰을 JWKS로 검증, 그룹 → 역할(admin > reviewer > employee). 개발 토큰 `dev:<sub>:<role>:<id>`와 테스트 계정 10개(`DEV_PROFILES`) |
| `domain.py` | 칸 목록(`AI_FIELDS`, `REQUIRED_FIELDS`, `FIELD_LABELS`), 분류 10개(`CATEGORIES`, 예전 코드 변환 `to_category`), `normalize_fields`(금액 정수·일시·카드번호), `run_checks`(검산·중복·같은 승인번호·심야·주말), `review_points`(검수자가 먼저 볼 것), `missing_required`, `ro`(로/으로) |
| `org.py` | 부서 7개(코드·설명), 직급 6개, 검수 부서(재무회계부), 관리자 코드 `ADM`, 사번 접두어 |
| `store.py` | DynamoDB 저장소 (아래) |
| `bedrock.py` | `call_tool()` — 도구 호출로 JSON 강제, 모델별 요청 조정 |

## DynamoDB 단일 테이블 (`receipt-flow-dev`)

| pk | sk | 내용 |
|---|---|---|
| `RECEIPT#{id}` | `META` | 증빙 본문: `owner_sub`, `owner_name`, `owner_profile`, `fields`, `analysis_status`, `review_status`, `needs_check`, `ai_filled`, `checks`, `result_confirmed_at`, `review_note`, `review_fields`, `preprocess`, `timings`, `model_usage`, `ai_context.items` |
| `RECEIPT#{id}` | `EVENT#{ts}` | 처리 이력 `{actor, action, note}` (화면 이름은 `web/src/labels.ts`의 `ACTION_LABEL`) |
| `RECEIPT#{id}` | `MSG#{ts}` | 대화 `{role: user|assistant|event, text, slot, choices, suggestions, actions, pending_suggestions}` |
| `DELETIONS` | 삭제 시각 | 관리자가 지운 증빙의 기록 (`log_deletion`/`list_deletions`, 최신순) |
| `USAGE` | `DAILY#<날짜>` | 소개 페이지 비용 카드의 하루 스냅샷 (`get_usage`/`put_usage`, `api_service/usage.py`) |
| `COUNTER` | `EMPNO#<코드><연도>` | 사번 순번 (원자적 증가 `next_sequence`) |

| 인덱스 | 키 | 쓰임 |
|---|---|---|
| `gsi1` | `gsi1pk=OWNER#{sub}`, `gsi1sk=created_at` | 내 증빙 목록, 중복·같은 승인번호 점검 |
| `gsi2` | `gsi2pk=STATUS#{review_status}`, `gsi2sk=updated_at` | 검수·관리자 상태별 목록 |

`store.py` 주요 함수: `create_receipt`, `get_receipt`, `update_receipt`(`expect={"review_status": (...)}`로 **상태 조건부 쓰기** — 그 사이 상태가 바뀌었으면 `ConflictError` → 409), `apply_fields`(칸 반영 + 점검 다시 계산), `list_by_owner`, `list_by_status`(화면 목록, 최대 `limit`건), `list_all_by_status`(페이지를 끝까지 읽음 — CSV 내보내기), `delete_receipt`(대화·이력까지, 상태 조건), `add_event`/`list_events`, `add_message`/`list_messages`/`delete_messages`, `log_deletion`/`list_deletions`/`delete_deletion`, `next_sequence`.
DynamoDB 숫자는 `Decimal`이라 `_plain`/`_ddb`가 오갈 때 변환합니다.

## 인증·권한

- 로그인은 브라우저가 Cognito에 직접 합니다. 서버는 **ID 토큰**만 받아 서명(JWKS)·발급자·클라이언트를 검사합니다. 비밀번호는 서버를 거치지 않습니다.
- 프로필(이름·사번·부서·직급)은 Cognito 사용자 속성(`custom:*`), 역할은 그룹. 관리자 API(`admin.py`)가 Cognito Admin API로 계정을 만들고 고칩니다 (임시 비밀번호는 응답으로 한 번만, 저장·로그 없음).
- 권한 규칙: 직원은 자기 증빙만, `draft`·`changes_requested`일 때만 수정·제출. 검수 담당자는 모두 조회, `submitted`만 승인·보완 요청. 관리자는 `/api/admin/*`와 공통 `/api/me`·`/api/meta`를 사용하며 일반 작성·대화·사진 보정 경로는 차단됩니다. 규칙의 원문은 [contract.md](contract.md).
- 검사: 검수 담당자 = 재무회계부, 관리자 = 부서 없음, 자기 자신 강등·중지·삭제 금지, 목록 밖 부서·직급 거부.

## 스크립트 (`services/scripts/`)

| 스크립트 | 하는 일 | AWS에 쓰나 |
|---|---|---|
| `dev.sh` | 서비스 4개 로컬 실행 | 공유 리소스 사용 |
| `make_env.py` | 본인 AWS 로그인으로 리소스를 **조회만** 해서 `.env` 두 개 작성 (`--force`, `--print`, `--dev-login`) | ❌ |
| `seed_users.py` | 첫 관리자 계정(admin1@dev.com) 만들기, 임시 비밀번호는 `demo-users.local.json`(git 제외) | ✅ Cognito |
| `issue_temp_password.py` | 임시 비밀번호 재발급 / `--set`으로 바로 정하기 | ✅ Cognito |
| `seed_dev_data.py` / `clear_dev_data.py` | 공용 개발 계정의 합성 샘플 생성(`seed` 표시 — 사진이 분석 큐에 들어가도 워커가 모델 없이 버림) / **모든 `dev-*` 소유 증빙·대화·이력·사진 삭제** (생성 스크립트가 넣은 것뿐 아니라 팀원이 직접 올린 개발 계정 데이터도 포함) | ✅ 테이블·S3 |
| `make_sample_receipt.py`, `eval/*` | 합성 영수증 이미지, 모델 평가 | ❌ (평가는 Bedrock 호출) |

공유 데이터에 쓰는 스크립트는 팀에 미리 알리고 담당자가 실행합니다. 특히 `clear_dev_data.py`는 실행자별 구분·확인 절차가 없으므로 각 팀원이 임의로 실행하지 않습니다. 개인 테스트 데이터는 본인이 만든 증빙만 개별 정리합니다.

## 테스트 (`services/tests/`, moto)

- `conftest.py`가 moto로 S3·SQS·DynamoDB를 흉내 내고 `RF_AUTH_MODE=dev`, `RF_AI_MODE=mock`으로 고정 → **실제 AWS·Bedrock을 쓰지 않음**. 토큰: `EMP`, `EMP2`, `REV` (관리자 테스트는 Cognito도 moto).
- 파일 이름은 영역 접두사: `test_api_*`(③), `test_chat_*`·`test_ocr_*`·`test_preprocess_*`(②), `test_common_*`(③), 서비스를 거치는 흐름 `test_flow.py`. 공통 도우미 `helpers.py` (`new_receipt`, `sse_done`, `_photo`).
- 새 API는 contract.md → 테스트 → 구현 순서. 테스트 수는 `uv run pytest --collect-only -q`로 확인합니다.

## 바꿀 때 체크리스트

### 변경 절차

1. API·필드·상태를 바꾸면 [contract.md](contract.md) 먼저 (관련 담당자 모두 리뷰), 웹 `api.ts` 타입도.
2. 새 AWS 권한이 필요하면 `infra/terraform/admin/iam.tf`의 서비스별 정책(④와 같이) — 배포에서는 그 권한만 갖습니다.
3. `uv run ruff format . && uv run ruff check . && uv run pytest`.
4. 개인정보·비밀값을 로그·테스트 데이터에 넣지 않기.
