# Receipt Flow — 서비스 계약 (API · 데이터 · 이벤트)

담당자 사이에 주고받는 규약입니다. 이 문서를 바꾸는 PR은 관련 담당자 모두가 리뷰합니다.

## 상태

| 필드 | 값 | 바꾸는 쪽 |
|---|---|---|
| `analysis_status` | `waiting` → `queued` → `processing` → `done` \| `failed` | api(업로드 완료), ocr-worker |
| `review_status` | `draft` → `submitted` → `approved` \| `changes_requested` → (수정) → `submitted` | api |

- 직원은 `draft`, `changes_requested` 상태에서만 수정·제출할 수 있다.
- 담당자는 `submitted` 상태만 승인하거나 보완 요청(사유 필수)할 수 있다.
- 직원은 본인 증빙만, 담당자(`reviewer` 그룹)는 모든 증빙을 조회한다.

## 필드

| 키 | 출처 | 필수(제출) |
|---|---|---|
| `merchant_name` 상호명 | AI | ✅ |
| `business_number` 사업자번호 | AI | |
| `transaction_at` 거래 일시 (`YYYY-MM-DD` 또는 `YYYY-MM-DDTHH:MM`, 초는 저장할 때 잘라 냄) | AI | ✅ |
| `supply_amount` 공급가액 (원, 정수) | AI | |
| `vat_amount` 부가세 | AI | |
| `exempt_amount` 면세금액 (면세물품가액·면세 합계. 인쇄된 `0`은 0, 없으면 `null`) | AI | |
| `total_amount` 총액 (할인·쿠폰 반영 후 최종 결제금액) | AI | ✅ |
| `payment_method` 결제수단 (카드사명으로 신용/체크 판단) | AI | |
| `card_issuer` 카드사 (찍힌 그대로, 예: 토스뱅크·KB국민체크) | AI | |
| `card_number` 카드번호 (영수증에 찍힌 그대로 저장·표시 — 일부만 찍혔으면 일부, 전체면 전체, 가려진 자리는 `*` 그대로. 앞뒤 공백만 정리) | AI | |
| `approval_number` 승인번호 (문자열, 앞자리 0 유지, 공백 제거. 거래·주문·전표번호 아님) | AI | |
| `category` 지출 분류 (아래 코드) | AI 제안 → 챗봇에서 직원 확인 | ✅ |
| `purpose` 지출 목적 | 챗봇 | ✅ |
| `department` 부서 | 로그인 프로필 (서비스에서 변경 불가, `PATCH` 시 `400 read_only_field`) | |

**지출 분류 코드** (저장은 코드, 화면·CSV는 이름. `GET /api/meta`가 목록을 준다)

| 코드 | 이름 | 포함 항목 |
|---|---|---|
| `food` | 식사·간식비 | 업무 식사, 야근 식사, 회식, 회의 다과, 탕비실 간식 |
| `entertainment` | 접대·선물비 | 업무상 접대 식사, 외부 관계자 선물·경조 화환 |
| `travel` | 교통·출장비 | 택시·대중교통, 주유·충전, 주차·통행료, 철도·항공, 숙박, 업무 차량 정비 |
| `delivery` | 우편·배송비 | 우편·등기, 택배, 퀵서비스, 샘플 발송 |
| `supplies` | 사무용품·소모품비 | 문구, 복사용지, 토너, 청소·구급용품, 컴퓨터, 모니터, 프린터, 책상·의자 |
| `education` | 도서·교육비 | 업무 관련 도서, 강의, 세미나, 직무교육 |
| `welfare_event` | 행사·복리후생비 | 워크숍, 사내 행사, 임직원 경조 화환·선물 |
| `subscription` | 통신·구독비 | 업무 전화·인터넷, 소프트웨어 구독, 클라우드, API, 호스팅 |
| `marketing` | 광고·홍보비 | 온라인 광고, 홍보물 인쇄, 판촉물 제작, 전시 부스 |
| `other` | 기타 업무비 | 시설·기기 수리 등 위 분류에 해당하지 않는 업무 지출 |

**분류 원칙** (직원의 증빙 제출용 분류이며, 최종 회계 계정은 회사 기준에 따라 연결한다)
- AI가 분류를 제안하고, 직원이 지출 목적을 확인한 뒤 확정한다.
- 식사·회식·회의 다과·탕비실 간식은 식사·간식비로 묶고 세부 목적을 지출 목적에 적는다.
- 접대·선물비는 영수증만으로 확정하지 않는다. 임직원 복지 목적의 선물은 행사·복리후생비.
- 교통·출장비는 교통·주유·충전·주차·통행료·숙박·차량 정비 같은 세부 항목을 지출 목적에 남긴다.
- 사무용품·소모품비는 사무기기·가구 구매도 포함하되, 세부 항목을 지출 목적에 적는다.
- 행사에서 따로 결제한 식사는 식사·간식비로 하고 지출 목적에 행사명을 적는다.
- 기타 업무비는 구체적인 사용 목적을 반드시 적는다.

`PATCH`는 코드와 이름을 모두 받는다 (`"식사·간식비"` → `food`). 목록에 없는 값은 `400 invalid_category`.
호환 입력 분류 코드는 읽을 때 현재 코드로 정규화한다: `meal`·`team_dinner`·`meeting` → `food`, `transport` → `travel`,
`postage` → `delivery` (나머지 코드는 그대로). 호환 이름("식대", "교통비" 등)도 받는다.

## 프로필 (로그인)

Cognito 사용자 속성 → ID 토큰 → `GET /api/me`. 직원·담당자 화면에서는 읽기 전용이고, **관리자**가 관리 화면(`/api/admin/users`)에서 만들고 고친다. 바뀐 프로필은 그 사람이 다음에 로그인(토큰 갱신)할 때 반영된다.

| 키 | Cognito 속성 | 예 |
|---|---|---|
| `name` 이름 | `name` | 김직원 |
| `employee_no` 직원코드(사번) | `custom:employee_no` | DEV2026001 (아래 규칙, 예전 계정은 E2026001) |
| `department` 부서 | `custom:department` | 영업부 (아래 목록) |
| `position` 직급 | `custom:position` | 대리 (아래 목록) |
| `role` 권한 | 그룹 `employee` / `reviewer` / `admin` (여러 그룹이면 admin > reviewer > employee) | employee (`role_label`: 직원 / 검수 담당자 / 관리자) |


**부서** (코드). 계정을 만들거나 고칠 때 이 목록에서만 고른다 (서버가 검사, 목록 밖이면 `400 invalid_department`). 예전 값은 그 계정을 고칠 때 그대로 둘 수 있다.

| 부서 · 코드 | 하는 일 |
|---|---|
| 경영지원부 `MGT` | 인사, 총무, 법무 |
| 재무회계부 `ACC` | 회계, 결산, 증빙 검토 (검수 담당자 소속) |
| 기획부 `PLN` | 사업·전략 기획 |
| 영업부 `SAL` | 국내외 영업 |
| 마케팅부 `MKT` | 광고, 홍보, 브랜드 |
| 개발부 `DEV` | 서비스 개발, 인프라, 데이터 |
| 감사부 `AUD` | 내부 감사, 준법 점검 |

**직급**: 사원 · 주임 · 대리 · 과장 · 차장 · 부장 (낮은 순, 목록 밖이면 `400 invalid_position`). 팀장 같은 직책(맡은 자리)은 지금 쓰지 않는다.

**검수 담당자는 재무회계부만** (만들거나 고칠 때 역할이 `reviewer`인데 부서가 재무회계부가 아니면 `400 reviewer_department`). 직급은 자유.

**사번** `employee_no` = 부서 코드 + 만든 해(올해) + 세 자리 순번 (예 `DEV2026001`). 계정을 만들 때 서버가 정하고 바꾸지 않는다 (부서를 옮겨도 그대로). 만드는 화면에는 보이지 않고 목록·수정 화면에서 본다.
순번은 부서·연도별로 001부터, DynamoDB 카운터(`pk=COUNTER`, `sk=EMPNO#<코드><연도>`)로 원자적으로 올린다. 카운터가 없으면 Cognito에 있는 같은 접두어의 가장 큰 번호 다음부터.

증빙을 만들 때 `owner_profile {employee_no, department, position}`을 증빙에 복사해 두고 (나중에 부서가 바뀌어도 작성 당시 기준 유지), `fields.department`를 프로필 부서로 채운다.

`needs_check`: AI가 읽지 못했거나 확신이 낮은 필드 키 목록. 직원이 그 필드를 수정하면 목록에서 빠진다.

`ai_filled`: AI가 채운 뒤 사람이 아직 손대지 않은 필드 키 목록 (ocr-worker 추출, 챗봇이 답변에서 추정한 분류·목적). 직원이 그 칸을 고치거나 챗봇에서 추천 분류를 직접 고르면 빠진다. 화면은 이 칸에 "AI"/"AI 추천" 표시를 붙인다.

`result_confirmed_at`: 직원이 결과 카드에서 "맞아요"를 누른 시각 (챗봇 `confirm_result`, mock 모드는 챗봇이 직접 기록). 다시 분석하면 `null`로 돌아간다. 화면은 이 값이 있으면 결과 카드 버튼을 숨긴다.

`checks`: 자동 점검 결과 목록 `{code, level: "error"|"warn", message}`
- `amount_mismatch` — 공급가액 + 부가세 ≠ 총액 (세 값이 모두 있을 때만)
- `late_night` — 22시~06시 거래, `weekend` — 주말 거래
- `duplicate` — 같은 제출자의 같은 상호·거래일·총액 증빙이 이미 있음
- `same_approval` — 같은 제출자의 같은 승인번호 증빙이 이미 있음 (다른 직원과의 중복은 승인번호 인덱스가 필요해 아직 미구현)

## HTTP API (api-service, prefix `/api`)

이 절의 요청은 `Authorization: Bearer <Cognito ID token>`이 필요합니다. 공개 API와 로컬 개발자 로그인 예외는 해당 절을 따릅니다.
직원만 증빙 생성·내 목록 조회·재촬영·업로드 완료·필드 수정·삭제·제출·사진 보정·챗봇 쓰기를 사용할 수 있습니다. 검수 담당자는 증빙 상세·대화 조회와 검수 API를 사용합니다. 관리자는 `/api/me`·`/api/meta`와 관리자 API를 사용하며 작성·검수·대화·사진 보정 경로는 `403 forbidden`입니다.
오류는 `{"error": {"code": "...", "message": "..."}}` 형식, 상태 코드 400/401/403/404/409/422.

| 메서드 · 경로 | 누가 | 설명 |
|---|---|---|
| `GET /api/me` | 모두 | 프로필 `{sub, email, name, employee_no, department, position, role, role_label}` |
| `GET /api/meta` | 모두 | `{categories: [{code, label, hint}], departments: [{code, name}], field_labels}` (부서는 필터 선택지) |
| `POST /api/receipts` | 직원 | 작성 중 증빙 생성 + 원본 업로드 URL(`raw/`) `{receipt, upload: {url, headers}}` |
| `POST /api/receipts/{id}/upload-url` | 직원 | 사진 다시 올리기용 원본 업로드 URL 재발급. 다른 영수증일 수 있으므로 **처음부터 다시**: 영수증 칸·지출 목적·분류·결과 확인(`result_confirmed_at`)·확인 필요·AI 표시를 비우고 대화 기록을 지운다. 부서(프로필)와 처리 이력은 남고 이력에 `reuploaded` |
| `POST /api/receipts/{id}/uploaded` | 직원 | 보정(`apply`)이 끝난 뒤 호출 → `analysis_status=queued` |
| `GET /api/receipts` | 직원 | 내 증빙 목록 (최신순, 사진 확정 전 `waiting` 증빙은 제외) |
| `GET /api/receipts/{id}` | 본인·담당자 | 증빙 상세 + `image_url`(보정본) + `original_url`(원본, 5분 유효) + `history` + `review_points` (아래) |
| `PATCH /api/receipts/{id}` `{fields: {...}}` | 본인 | 필드 수정. 수정할 수 없는 칸은 `400 unknown_fields` |
| `POST /api/receipts/{id}/submit` | 본인 | 분석 중(`waiting`·`queued`·`processing`)이면 `409 analysis_pending`, 필수 항목이 비면 `422 missing_fields`, 오류 수준 점검(`level: "error"`, 예: 검산 불일치)이 있으면 `422 check_failed`. 통과하면 제출 |
| `DELETE /api/receipts/{id}` | 본인 | 작성 중(`review_status=draft`, 한 번도 제출 안 한 것)만 영구 삭제 → `204`. 증빙·대화·처리 이력·사진(원본 `raw/`, 보정본 `incoming/`)을 모두 지운다. 제출·보완 요청·승인된 증빙은 `409 not_deletable`. 분석 중에 지워지면 워커는 그 메시지를 버린다 |
| `GET /api/review/receipts?status=submitted` | 담당자 | 상태별 목록. 각 항목에 `review_points`. 화면은 먼저 제출된 순(선입선출)으로 보여 주고, 오류·주의가 있는 건은 색·표시로 강조하고, 검수 목록에 **"주의" 탭**을 둔다(웹 주소 `/review?status=flagged`). 실제 API는 `status=submitted` 목록을 받고 웹에서 오류·주의 항목을 필터링한다. API의 허용 상태는 `submitted`·`approved`·`changes_requested`·`draft`이며 `status=flagged`를 API에 보내면 `422`다. 홈의 "주의·오류" 숫자는 이 탭으로 연결 |
| `POST /api/review/receipts/{id}/approve` | 담당자 | 승인 |
| `POST /api/review/receipts/{id}/request-changes` `{reason, fields?}` | 담당자 | 보완 요청. `fields`: 다시 봐야 할 칸 (`photo`는 사진 다시 찍기, 목록 밖이면 `400 unknown_fields`). `review_note`·`review_fields`로 저장 |
| `GET /api/review/export.csv?month=YYYY-MM&status=all\|approved` | 담당자 | 월별 CSV (사번·제출자·직급·상태 + 모든 증빙 칸 + 제출일시·검수자·검수일시·보완 요청 사유). 달은 **거래 일시** 기준, 거래 일시순. `status=all`(기본): 작성 중을 뺀 전체(제출·보완 요청·승인), 파일 이름 `receipts-YYYY-MM.csv`. `status=approved`: 승인 건만(정산용) + 맨 아래 합계 줄(건수, 금액 칸 합), 파일 이름 `receipts-YYYY-MM-approved.csv`. 그 밖의 값은 `400 invalid_request`. 건수 제한 없이 모두 담는다. 엑셀 수식 실행을 막으려고 `= + - @`·탭·줄바꿈으로 시작하는 글자 칸은 앞에 `'`를 붙인다(숫자 칸은 그대로) |

**검토 포인트 `review_points`** — 승인자가 먼저 볼 것을 서버가 규칙으로 뽑은 목록 `[{level: "error"|"warn"|"info", code, text, fields}]`.
`code`는 포인트 종류, `fields`는 관련 칸 키 목록(없으면 `[]`). 화면은 `code`로 보완 요청 문구를 고르고 `fields`를 고칠 칸으로 쓴다.

| `code` | 내용 | `fields` |
|---|---|---|
| `amount_mismatch` · `late_night` · `weekend` · `duplicate` · `same_approval` | 점검 결과 (`checks`와 같은 코드·문구) | `[]` |
| `unclear_fields` | 흐리게 읽혀 확인 안 된 칸 | 해당 칸 |
| `analysis_failed` | AI가 읽지 못해(`analysis_status=failed`) 직원이 직접 입력함 | `[]` |
| `edited_fields` | AI가 읽은 뒤 직원이 직접 입력·수정한 칸 (금액 칸이 있으면 `warn`, 아니면 `info`) | 해당 칸 |
| `result_unconfirmed` | 직원이 AI 결과 확인을 건너뜀 | `[]` |
| `entertainment` | 접대·선물비 — 목적에 상대 거래처가 있는지 | `["purpose"]` |
| `other_category` | 기타 업무비 — 목적이 구체적인지 | `["purpose"]` |
| `short_purpose` | 지출 목적이 짧음 | `["purpose"]` |

**보완 요청 → 다시 제출**: 직원이 보완 요청된 증빙을 열면 화면이 `event: "changes_requested"`를 보낸다. 서버가 모델 없이
"담당자 ○○님이 보완을 요청했어요: “사유”"와 고칠 칸 안내를 답하고, 고칠 칸이 있으면 [직접 수정] (사진이면 [다시 찍기])을 붙인다.
고친 뒤에는 같은 최종 확인 카드를 거쳐 다시 제출한다 (`changes_requested` → `submitted`).
최초 보완 안내는 하단 [제출하기]로 내용을 확인하고 다시 제출하도록 안내한다. [수정 완료]는 [직접 수정]을 선택한 뒤의 대화 버튼이므로 최초 안내에서 필수 단계처럼 안내하지 않는다.

## 공개 API (api-service, 로그인 불필요)

| 메서드 · 경로 | 설명 |
|---|---|
| `GET /api/public/usage` | 소개 페이지의 팀 AWS 사용량 카드. `{label, spent, limit, remaining, percent, currency: "USD", start, end, days_left, as_of}`. **매일 09:00(KST) 기준 날짜 키로 캐시하는** 스냅샷: 해당 날짜 키가 없을 때 AWS Budgets 예산(`RF_USAGE_BUDGET`, 기본 `aws-team4-receipt-flow`)을 읽어 DynamoDB(`pk=USAGE`, `sk=DAILY#<날짜>`)에 저장하고, 이후 같은 날짜 키의 저장된 값을 사용한다. 최초 동시 요청에는 조회·저장이 중복될 수 있으며 정확히 한 번 실행을 보장하지 않는다. 예산을 읽을 수 없으면 `503 usage_unavailable` (화면은 카드를 유지하고 금액 대신 `—`·오류 안내를 표시). 금액·예산 외 정보는 주지 않는다 |

## 관리자 API (api-service, prefix `/api/admin`, 관리자만 — 아니면 `403 forbidden`)

관리자는 **관리만** 한다 (증빙 작성·검수 화면 없음). 계정은 Cognito 사용자 풀에서 직접 다룬다 (`username` = Cognito 사용자 이름, 이메일로 만든다).

| 메서드 · 경로 | 설명 |
|---|---|
| `GET /api/admin/options` | 계정 폼 선택지 `{departments: [{code, name, description}], positions, reviewer_department}` |
| `GET /api/admin/users` | 계정 목록 `{items: [{username, email, name, employee_no, department, position, role, role_label, status, enabled, created_at}]}`. `status`: `FORCE_CHANGE_PASSWORD`(첫 로그인 대기) · `CONFIRMED`(사용 중) 등 Cognito 값 그대로 |
| `POST /api/admin/users` `{email, name, department, position, role}` | 계정 생성 → `201 {user, temporary_password}`. 사번은 서버가 만든다 (위 규칙). **관리자는 부서 없음** (`department` 무시, 사번은 `ADM`+연도+순번). 이메일은 보내지 않고 임시 비밀번호를 **이 응답에서 한 번만** 돌려준다 (서버에 저장·기록하지 않음). 첫 로그인 때 새 비밀번호를 정한다. 같은 이메일이 있으면 `409 user_exists` |
| `PATCH /api/admin/users/{username}` `{name?, department?, position?, role?}` | 프로필·역할 수정 → `{user}`. 사번은 바꾸지 않는다. 이미 낸 증빙의 `owner_profile`은 바꾸지 않는다 (제출 당시 기준). 자기 자신의 `admin` 역할은 뺄 수 없다 (`409 self_demote`) |
| `POST /api/admin/users/{username}/temporary-password` | 새 임시 비밀번호 발급 → `{temporary_password}` (한 번만). 다음 로그인 때 새 비밀번호를 정해야 한다 |
| `POST /api/admin/users/{username}/disable` · `/enable` | 사용 중지 / 다시 사용 → `{user}`. 중지된 계정은 로그인할 수 없고, 낸 증빙은 남는다. 자기 자신은 중지할 수 없다 (`409 self_disable`) |
| `DELETE /api/admin/users/{username}` | 계정 영구 삭제 → `204` (Cognito에서 지움, 되돌릴 수 없음). 그 사람이 낸 증빙은 남는다 (제출자 이름 그대로). 자기 자신은 지울 수 없다 (`409 self_delete`) |
| `GET /api/admin/receipts?status=draft\|submitted\|changes_requested\|approved` | 상태별 전체 증빙 (작성 중 포함) `{items}` |
| `DELETE /api/admin/receipts/{id}` | 상태와 상관없이 영구 삭제 → `204`. 증빙·대화·처리 이력·사진(원본 `raw/`, 보정본 `incoming/`)을 지우고 **삭제 기록**만 남긴다 |
| `GET /api/admin/deletions` | 삭제 기록 (최신순) `{items: [{key, receipt_id, deleted_at, deleted_by, owner_name, merchant_name, total_amount, review_status}]}` |
| `DELETE /api/admin/deletions/{key}` · `DELETE /api/admin/deletions` | 삭제 기록 한 건 / 모두 지우기 → `204` (`key`는 목록의 값, URL 인코딩) |

역할 값 `role`: `employee` · `reviewer` · `admin`. 역할을 바꾸면 Cognito 그룹을 그 하나로 맞춘다.

## 개발자 로그인 (로컬 전용)

`RF_DEV_LOGIN=true`(로컬 `services/.env`에만)일 때 서버는 Cognito 토큰과 함께 `Bearer dev:<sub>:<role>:<id>` 개발 토큰도 받는다.
배포 설정(`deploy/k8s`)에는 없으므로 꺼져 있다. `RF_AUTH_MODE=dev`(자동 테스트)는 개발 토큰만 받는다.

| 메서드 · 경로 | 설명 |
|---|---|
| `GET /api/dev/profiles` (로그인 불필요) | 테스트 계정 10개 `{items: [{id, name, role, role_label, department, position, employee_no}]}`. 개발자 로그인이 꺼져 있으면 `404` |

화면: 로컬 개발 서버(`npm run dev`)에서는 로그인 화면 아래 "개발자 모드" 링크로 목록을 연다. 기본 Cognito 배포 빌드에서는 링크가 숨겨지고 서버도 개발자 인증을 허용하지 않는다. 로컬 컨테이너 검증용 `AUTH=dev`는 별도 dev 인증 빌드 경로이며 실제 배포에 사용하지 않는다.
테스트 데이터는 `scripts/seed_dev_data.py`로 넣고 `scripts/clear_dev_data.py`로 개발 계정(`owner_sub`가 `dev-`로 시작) 것만 지운다.

## chat-service (prefix `/chat`)

| 메서드 · 경로 | 설명 |
|---|---|
| `POST /chat/receipts/{id}/turn` `{message?: string, event?: "start" \| "analysis_done" \| "changes_requested", choice?: {purpose, category}}` | 사용자 말 또는 화면 이벤트에 AI가 답하고, 필요하면 도구로 증빙을 고친다. SSE로 스트리밍. `choice`는 추천 버튼을 누른 것: 모델을 부르지 않고 목적·분류를 바로 저장한다 |
| `GET /chat/receipts/{id}/messages` | 대화 기록 (`role`: user·assistant만, 이벤트는 제외). assistant 메시지에는 그때 붙인 `choices`·`suggestions`가 있어 새로 열어도 버튼을 다시 보여 준다 |

**AI 어시스턴트 (도구를 쓰는 챗봇, `RF_AI_MODE=bedrock`)** — 모델은 `RF_CHAT_MODEL`.
매 턴마다 지금 증빙 상태(필드·확인 필요·점검 결과·분석 상태·AI가 채운 칸), 작성자 프로필, 품목 요약(`ai_context.items`), 같은 가게의 과거 증빙(최대 3건)을 보고 답한다.

| 도구 | 하는 일 |
|---|---|
| `update_fields` | 사용자가 **말한 값**으로 칸을 고친다 (AI_FIELDS + `purpose`). 부서·프로필은 고칠 수 없다. 처리 이력에 `ai_edited` |
| `set_category` | 지출 분류 설정. `confirmed_by_user=false`면 추천(`ai_filled`에 남음) |
| `confirm_result` | 사용자가 AI가 읽은 결과가 맞다고 확인 → `result_confirmed_at` |
| `show_choices` | 다음 답에 쓸 버튼(최대 8개). 예/아니요로 답할 질문이면 `["예", "아니요"]` |
| `suggest_expense` | 영수증 맥락(품목·가게·시간대·과거 증빙·부서)으로 고른 목적·분류 쌍 추천 2~3개 → 화면에 추천 버튼과 [직접 입력] |
| `check_submission` | 빠진 필수 항목·오류 점검. 준비됐으면 화면에 제출 버튼을 띄운다 |

- AI는 제출하지 않는다 (제출은 사람이 버튼으로). 사용자가 말하지 않은 값을 지어 넣지 않는다 — 추천은 묻는 형태로.
- 이벤트: `analysis_done`(분석이 끝났을 때 — AI가 결과를 보여 주고 확인을 받는다), `changes_requested`(아래 보완 요청). 서버는 `start`(대화 처음 열 때, 이미 답한 대화면 무시)도 받지만 현재 웹은 보내지 않는다. 이벤트는 대화 기록에 `role: "event"`로 저장되고 화면엔 안 보인다.
- **한 번에 하나씩 — 결과 확인이 먼저.** `analysis_done`(결과 확인 전)의 답은 서버가 정한 문장 "영수증을 읽었어요. 내용이 맞는지 확인해 주세요."이다 (흐린 칸·금액 검산 오류가 있으면 그것만 덧붙임). 같은 턴에 AI가 목적·분류 추천을 미리 만들어 메시지의 `pending_suggestions`에 두고, 화면에는 아직 보내지 않는다.
- 결과 카드의 [맞아요]·[직접 수정]과 [수정 완료]는 일반 메시지로 보낸다. 서버가 모델 없이 답한다.
  - [맞아요]·[수정 완료] → `result_confirmed_at` 기록 → 주의 경고(심야·주말·중복)를 한 문장으로 짚고 "어떤 일로 쓰신 비용인가요?"라고 물으며 미리 만든 추천(`suggestions`)을 붙인다. 목적·분류가 이미 있으면 다음 할 일(제출 등)을 안내한다.
  - [직접 수정] → 폼에서 고치도록 안내하고 `choices: ["수정 완료"]`. (예전 문구 "고칠게요"·"다 고쳤어요"도 받음)
- 직원이 카드를 건너뛰고 바로 목적을 말해도 그대로 받는다 (순서를 강제하지 않음).
- 웹은 분석 중에는 `start`를 보내지 않는다 (분석 중 답이 결과 카드 아래에 남아 지난 메시지처럼 보이므로). 첫 말은 `analysis_done`에서 한다.

SSE 이벤트: `delta` `{text}` → (`tool` `{name, summary}`)* → `done` `{text, choices, suggestions, actions, changed, fields}`.
`suggestions`: `[{purpose, category, category_label}]` — 누르면 `choice`로 보낸다. 처리 이력에는 `edited` "AI 추천 선택".
`actions`: `["submit"]`이면 화면이 **최종 확인 카드**(상호·일시·총액·결제수단·분류·목적·부서와 주의 경고)를 [직접 수정]·[제출하기]와 함께 보여 준다. 카드는 그 메시지 바로 아래, 대화 흐름 안에 놓인다 (assistant 메시지에 `actions`가 저장돼 다시 열어도 같은 자리). 버튼은 마지막 카드에만 있고, 이전 카드는 한 줄로 접힌다. 제출한 뒤에는 "제출한 내용"으로 남는다. 아래 버튼 줄의 [제출하기]도 같은 카드를 거친다 (오류가 있으면 제출 불가). `changed`: 도구로 증빙이 바뀌었으면 true (화면이 다시 불러온다).

**테스트·mock (`RF_AI_MODE=mock`)**: 모델 없이 정해진 질문(목적 → 분류 확인)으로 동작한다 (`chat-service/dialog.py`). 결과 카드의 [맞아요]는 바로 `result_confirmed_at`을 기록하고, [직접 수정]은 답으로 해석하지 않는다. 목적 질문에는 과거 증빙·기본 예시로 만든 `suggestions`를 붙인다.

## preprocess-service (prefix `/preprocess`)

사진 보정은 서버에서 하고, 사람이 그 사이에 테두리를 확인·수정한다.

1. 브라우저가 원본(긴 변 최대 3200px, JPEG 품질 0.92)을 `raw/{id}.jpg`로 올린다.
2. `POST /preprocess/receipts/{id}/detect` → `{found, corners, width, height, blur_score, blurry, blur_min}`
   - `corners`: 원본 픽셀 기준 네 점(왼쪽 위·오른쪽 위·오른쪽 아래·왼쪽 아래). 못 찾으면 `found=false`와 가장자리에서 6% 들어온 기본 틀.
   - `blurry`: 흐림 점수(라플라시안 분산, 긴 변 1000px 기준)가 60 미만.
3. 화면에서 사용자가 모서리를 끌어 맞춘다.
4. `POST /preprocess/receipts/{id}/apply` `{corners: [[x,y]×4] | null}` → 원근 보정·긴 변 2400px(JPEG 품질 92)로 `incoming/{id}.jpg` 저장 (분석 시작). `null`은 자르지 않고 원본 그대로.
   응답·`receipt.preprocess`: `{where: "server", corners, detected_corners, adjusted, blur_score, width, height, elapsed_ms}`. 모양이 이상한 네 점은 `422 bad_corners`.
5. `POST /api/receipts/{id}/uploaded`

원본은 `raw/`에 남아 검수 화면의 "원본" 보기로 쓴다 (90일 뒤 자동 삭제).

## S3 · SQS

| 키 | 의미 |
|---|---|
| `raw/{id}.jpg` | 사용자가 올린 원본 (검수자 원본 보기) |
| `incoming/{id}.jpg` | 보정본 = 분석 대상. 생성 시 S3 이벤트 → SQS → ocr-worker |

## DynamoDB (단일 테이블)

| pk | sk | 내용 |
|---|---|---|
| `RECEIPT#{id}` | `META` | 증빙 본문. `gsi1pk=OWNER#{sub}`, `gsi1sk=created_at`, `gsi2pk=STATUS#{review_status}`, `gsi2sk=updated_at` |
| `RECEIPT#{id}` | `EVENT#{ts}` | 처리 이력 `{actor, action, note}` |
| `RECEIPT#{id}` | `MSG#{ts}` | 챗봇 대화 `{role, text}` |

`timings` (단계별 시각, ISO8601): `created`, `uploaded`, `analysis_started`, `analysis_finished`, `chat_first_question`, `chat_last_answer`, `submitted`. 워커는 `model_usage {input_tokens, output_tokens, latency_ms}`도 기록한다.
