# 웹 화면 (`web/`) — ① 장차희

React 18 + React Router 6 + Vite + TypeScript (`web/package.json` 기준). 상태 관리 라이브러리·UI 라이브러리 없이 순수 CSS(변수)로 AWS 콘솔 느낌을 냅니다.
전체 그림은 [architecture.md](architecture.md), 서버와의 약속은 [contract.md](contract.md).

## 실행·빌드

도구 설치·AWS 로그인·환경 파일 생성·백엔드와 웹을 함께 실행하는 순서는 [로컬 개발 시작하기](local-setup.md)를 따릅니다.

```bash
cd web && npm install && npm run dev        # http://localhost:5173 (백엔드 8000–8002로 프록시)
npm run build                               # 타입 검사 + 배포 빌드 (CI 필수 검사 "web")
node --test tests/*.test.mjs                  # 검수 정렬·분석 시간·보완 사유 문구 회귀 검사
```

| 환경 변수 (`web/.env.local`, git 제외) | 뜻 |
|---|---|
| `VITE_AUTH_MODE` | `cognito`(기본) · `dev`(역할 선택 로그인, `npm run dev:devauth` + 백엔드 `RF_AUTH_MODE=dev`) |
| `VITE_REGION`, `VITE_COGNITO_CLIENT_ID` | Cognito 위치. `services/scripts/make_env.py`가 만들어 줌 |

- 개발 서버 프록시(`vite.config.ts`): `/api`→8000, `/chat`→8001, `/preprocess`→8002. 배포에서는 ALB가 같은 경로로 나눕니다 — **화면 코드는 상대 경로만** 씁니다.
- 배포 이미지: `web/Dockerfile`(빌드) + `web/nginx.conf`(정적 파일, SPA 새로고침 대응).

## 구조

```
src/
  main.tsx            진입점 (styles.css 불러옴)
  App.tsx             로그인 확인 → 역할(employee/reviewer/admin)별 라우트, 공통 껍데기(Shell)·도움말(HelpProvider)
  api.ts              API 호출(request), 타입(Receipt·Fields·Me…), 채팅 SSE(streamTurn), 사진 PUT
  auth.ts             Cognito 로그인 (InitiateAuth·새 비밀번호·토큰 갱신·비밀번호 변경), 개발자 로그인 토큰
  labels.ts           칸 이름, 분류·상태 라벨, 금액·날짜 표시 (won, txDate, shortDate)
  search.ts           목록 빠른 검색 (상호·금액·목적·승인번호·날짜·사번…, 띄어쓰기·대소문자 무시)
  recent.ts later.ts  브라우저 저장: 최근 연 증빙, 검수 "건너뛰기" 순서 (userStore.ts가 사용자별로 나눔)
  reviewOrder.ts      제출 시각을 실제 시각으로 비교 (Z/+09:00 혼합 지원), 건너뛰기 순서 유지
  analysisTime.ts     워커 분석 시작~완료 시간 (대기열 대기 제외), 과거 데이터 대체값 처리
  reviewReasons.ts    보완 요청 항목: 검토 포인트(`code`)·칸·사진 문구, 요청 합치기(`{reason, fields}`)
  image.ts            사진 줄이기(캔버스) → JPEG
  pages/              화면 단위
  components/         공통 부품
  styles.css          아래 파일을 순서대로 import만 (순서 = 덮어쓰기 우선순위)
  styles/             base(변수·버튼·표·칩) · shell(상단바·메뉴·도움말) · receipt · login · profile · review · home · admin
```

## 라우트 (역할별)

| 경로 | 직원 | 검수 담당자 | 관리자 |
|---|---|---|---|
| `/` (로그인 전) | 소개 페이지 `Landing` | ← | ← |
| `/about` (로그인 전·후) | 소개 페이지. 로그인 상태면 앱 틀 밖 전체 화면, 로그인 버튼 대신 "내 홈으로". 왼쪽 메뉴 맨 아래 "서비스 소개"·도움말 패널 아래 링크로 들어감 | ← | ← |
| `/login` | `Login` (+ 로컬 개발 서버에서만 "개발자 모드") | ← | ← |
| `/` | `EmployeeDashboard` 홈 | `ReviewerDashboard` 홈 | `AdminUsers` 계정 관리 |
| `/receipts?status=&cat=&q=` | `EmployeeHome` 내 증빙 | | |
| `/new`, `/receipts/:id/photo` | `NewReceipt` 촬영·업로드·테두리 확인 (다시 찍기) | | |
| `/receipts/:id` | `ReceiptWorkspace` 사진 · AI 어시스턴트 · 증빙 정보 | | |
| `/review?status=&dept=&cat=&q=` | | `ReviewHome` 검수 목록 (`status`: submitted·flagged·changes_requested·approved) | |
| `/review/:id` | | `ReviewDetail` 상세·승인·보완 요청·건너뛰기 | |
| `/admin/receipts?status=` | | | `AdminReceipts` (`deleted` = 삭제 기록) |
| `/me` | `Profile` 내 프로필·비밀번호 변경 | ← | ← |

## 화면 규칙 (지켜 주세요)

1. **AWS 콘솔 느낌**: 어두운 상단바(로고·메뉴·사용자) → 흰 막대(☰ · 현재 위치 · ⓘ) → 본문. 홈은 요약 줄(숫자 → 누르면 걸러진 목록) + 위젯. 목록은 표 + 상태 칩.
2. **상태는 주소에**: 탭·필터·검색을 `?status=&cat=&q=`에 둡니다(`useSearchParams`). 홈 숫자·왼쪽 메뉴가 그 주소로 바로 가고, 상세에서 "← 목록으로"가 같은 보기로 돌아옵니다. 상세로 갈 때 `navigate(path, { state: { from } })`로 돌아올 곳을 넘깁니다.
3. **색·간격은 `styles/base.css`의 `:root` 변수**만 씁니다 (`--blue`, `--ink`, `--line`, `--panel` …). 새 스타일은 그 화면 영역 파일에.
4. **모든 폭에서 깨지지 않게**: 375 / 768 / 1024(왼쪽 메뉴 열림) / 1440 / 1920px에서 상자 밖으로 삐져나가는 게 없어야 합니다.
   - 위젯은 `container-type: inline-size` — 위젯 안은 **화면 폭이 아니라 위젯 폭**으로 반응(`@container`). 왼쪽 메뉴가 열려 좁아질 때 때문.
   - 표는 `.table-wrap`(가로 스크롤). 휴대폰(≤720px)에서는 같은 목록의 `.cards`가 있으면 카드로 바꿉니다. 직원·검수·관리자 목록 모두 카드가 있으며, 행 버튼은 표와 카드가 같은 함수(`actions` 등)를 씁니다. 관리자 표는 칸 안에서 글자를 끊지 않습니다(`admin-table`).
   - 휴대폰(≤480px)은 상단 메뉴를 숨기고 ☰ 메뉴로 이동합니다.
   - 고정 폭 열(`110px 1fr 96px` 같은)은 쓰지 말고 `minmax(…)`·`max-content`로.
5. **문구는 한국어 존댓말**, 짧게. 오류는 서버 `error.message`를 그대로 보여 줌.
6. **서버가 정한 것은 화면이 다시 판단하지 않음**: 검토 포인트(`review_points`), 점검(`checks`), 제출 가능 여부는 서버 값을 표시만.

## 공통 부품 (`components/`)

| 부품 | 하는 일 |
|---|---|
| `Shell` | 상단바, 로고 아래 막대, 왼쪽 메뉴 자리, `SubNav`(현재 위치 — 막대 안으로 portal) |
| `Sidebar` | 역할별 탭 바로가기. 기본 접힘, 넓은 화면은 펼침 상태 기억, 휴대폰은 겹쳐 열리고 고르면 닫힘 |
| `Help` | "정보" 링크 → 오른쪽 도움말 패널(휴대폰은 아래 시트). 주제: 분류·금액·점검·검토 포인트·상태·사진. ⓘ는 지금 "상태" 고정 |
| `ChatPanel` | AI 어시스턴트: 진행 표시(사진→보정→읽기→결과 확인), 결과 카드, 대화, 추천·선택 버튼, 최종 확인 카드, SSE 스트리밍 |
| `FieldForm` | 증빙 정보 폼 (AI 표시·확인 필요 표시·필수 칸), 대화에서 "직접 수정"하면 해당 칸으로 이동 |
| `ReceiptParts` | `PhotoPanel`(보정본/원본 전환·다시 찍기), `SubmitReview`(최종 확인 카드), `Checks`, `History` |
| `CornerEditor` | 사진 위 네 모서리 끌기 (원본 픽셀 좌표) |
| `Widget`, `Metric`, `AmountBars` | 홈 위젯, 숫자 행, 금액 막대 |
| `RecentReceipts` | 최근 연/올린/처리한 증빙 탭 위젯 |
| `StatusChip`, `ReviewFlags`, `SearchBox` | 상태 칩, 오류·주의 표시, 검색 칸 |
| `landing/` | 소개 페이지 그림·애니메이션 (아키텍처 그림, 단계 데모 등), `UsageCard`("AWS 비용" 섹션 — `GET /api/public/usage`, 실패하면 "불러올 수 없어요"), `Team`("만든 사람들" — 아키텍처와 AWS 비용 사이, 영역별 담당 4명·GitHub 프로필·팀 저장소 링크, 화면 코드에 고정) |

## 소개 페이지 규칙

- 섹션은 처음부터 화면에 있어야 스크롤 등장 효과(`.reveal`)가 붙습니다 — 비동기로 받은 값은 섹션 안에서 채우기.
- 호버는 **과하지 않게**: 카드가 2~4px 뜨고, 색은 **테두리 바깥에만** 얇게 번지게 합니다(기능 카드·팀 카드·AWS 비용). 카드 면 전체를 물들이거나 큰 알록달록한 면을 쓰지 않습니다. 번짐 층(`::before`) 위에는 불투명한 바닥 층을 깔아 면이 물들지 않게 합니다. 마우스 기기에서만(`@media (hover: hover)`).
- "AWS 비용" 카드는 API 서버가 켜져 있어야 숫자가 나옵니다 (로컬은 `scripts/dev.sh`).

## 중요한 흐름

- **보완 요청 작성** (`ReviewDetail`): 문제를 본 자리에서 요청 항목을 담습니다. 검토 포인트의 [요청에 담기]는 서버가 준 `code`·`fields`로 문구와 고칠 칸을 정하고(검토자 참고용 포인트에는 버튼 없음), 작성 중에는 증빙 정보 칸마다 [수정 요청]이 생겨 제출된 값을 넣은 문구(예: "총액(90,000원)을 …")를 담습니다. 사진 다시 찍기(흐림·잘림)는 작성 칸에서 고르며, 다른 항목과 함께 고르면 다시 찍기로 모든 칸이 비워진다고 알립니다. 담은 항목은 분류 칩(예: "심야 사유", "총액")으로 보이며 고칠 칸을 정합니다. 상세 사유는 선택이며, 적으면 그 내용만, 비워 두면 담은 항목의 기본 문구(같은 문구는 한 번)를 `reason`으로 보내고(기존 `{reason, fields}`), 보내기 전에 직원 챗봇에 보일 메시지를 미리 보여 줍니다. 500자·고칠 칸 10개를 넘으면 보내기를 막습니다(잘라 내지 않음). 작성 칸은 증빙 정보 바로 아래에 열리며(대화·처리 이력보다 위), 포인트·칸에서 담을 때 화면 위치는 그대로입니다. [보완 요청] 버튼도 넓은 화면에서는 위치를 유지하고, 휴대폰(≤900px)에서는 작성 칸으로 이동합니다(사진 아래 멀리 열리기 때문).
- **로그인** (`auth.ts`): 브라우저가 Cognito에 직접 `InitiateAuth(USER_PASSWORD_AUTH)`. 관리자가 만든 계정은 `NEW_PASSWORD_REQUIRED` → 새 비밀번호. 토큰은 메모리+저장소, 만료 1분 전 갱신. 서버에는 ID 토큰만 보냄.
- **개발자 로그인**: `import.meta.env.DEV`일 때만 링크 표시 → `GET /api/dev/profiles` → `dev:<sub>:<role>:<id>` 토큰. 기본 Cognito 배포 빌드에서는 링크가 숨겨지며 서버의 `RF_DEV_LOGIN`도 꺼집니다. 서버가 `RF_DEV_LOGIN=false`이고 `RF_AUTH_MODE=cognito`이면 목록 API는 404입니다. 로컬 컨테이너의 `AUTH=dev`는 별도 인증 모드로 빌드되며 실제 배포에 사용하지 않습니다.
- **새 영수증** (`NewReceipt`): 파일·카메라 → 긴 변 최대 3200px로 줄임(`ORIGINAL_MAX_SIDE`) → `POST /api/receipts`(또는 다시 찍기 `upload-url`) → S3 PUT → `detect` → `CornerEditor` → `apply` → `uploaded` → `/receipts/:id`.
- **로컬 사진 분석**: 누구의 워커든 공용 큐의 사진을 처리하고, 모든 워커가 꺼져 있으면 분석이 대기합니다. [worker.md](worker.md).
- **분석 완료 감지**: `ReceiptWorkspace`가 분석 중(`waiting`·`queued`·`processing`)인 동안 1.5초마다 `GET /api/receipts/{id}`로 다시 불러옵니다 (푸시 없음).
- **AI 대화** (`ChatPanel` + `api.streamTurn`): 분석이 끝나면 `analysis_done` 이벤트 1번, 이후 사용자 말·버튼. SSE `delta`(글자) → `tool`(한 일 한 줄) → `done`(버튼·추천·`actions`). `done.changed`면 증빙을 다시 불러옴. `actions: ["submit"]`이면 그 메시지 아래 최종 확인 카드. 휴대폰(≤900px)에서 입력창을 누르면 화면 가운데로 스크롤합니다(하단 제출 막대·키보드에 가리지 않게).
- **보완 요청된 칸 표시** (`FieldForm`): `changes_requested` 상태에서 `review_fields`의 칸은 빨간 테두리와 "보완 요청" 태그로 표시하고, 폼 맨 위에 요청된 칸 목록(사진이면 "사진 다시 찍기")을 보여 줍니다. 다시 제출하면 사라집니다.
- **직원 보완 안내**: 최초 안내는 [제출하기]로 내용을 확인하고 다시 제출하도록 안내합니다. [수정 완료]는 [직접 수정] 선택 후의 대화 버튼이며 필수 재제출 단계가 아닙니다. 사진 보완은 기존 재촬영 흐름을 따릅니다.
- **건너뛰기**: 검수는 브라우저에 건너뛴 순서를 저장(`later.ts`)해 돌아가며, 직원은 할 일(보완 요청 → 작성 중)을 돌아가며.

## 검사

- `npm run build` (CI). 화면 변경은 브라우저로 확인하고, 폭 점검(위 4번)을 합니다.
- 자동 화면 테스트는 아직 없습니다.
