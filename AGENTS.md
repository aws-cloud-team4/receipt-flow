# 개발 지침 (사람·AI 에이전트 공통)

팀원 4명과 각자의 코딩 에이전트(Claude Code, Codex, Kiro 등)가 모두 이 규칙을 따릅니다.
서비스 소개와 로컬 실행은 [README.md](README.md), **전체 구조·현재 구현 상태·남은 일은 [docs/architecture.md](docs/architecture.md)**, API·필드·상태 규약은 [docs/contract.md](docs/contract.md).
영역별 내부 구조: [docs/ui.md](docs/ui.md) · [docs/ai.md](docs/ai.md) · [docs/backend.md](docs/backend.md) · [docs/aws.md](docs/aws.md). 코드를 바꿔 문서와 달라지면 같은 PR에서 문서도 고칩니다.

**문서는 현재 상태만 설명합니다.** 개발 일지, 수정 전후 과정, 폐기한 설정·모델 비교는 남기지 않습니다. 과거 내용은 현재 오류의 원인·해결·재발 방지에 필요한 경우만 문제 해결 안내로 남깁니다. 테스트 수치는 가장 최근 결과와 대상·측정 조건·측정일·한계만 유지하며, 현재 버전에서 재검증하지 않은 결과를 현재 성능으로 단정하지 않습니다. 변경 이력은 Git·PR에서 확인합니다.

## 건드리면 안 되는 것

- **규약 먼저.** API·필드·상태·이벤트를 바꿀 때는 `docs/contract.md`를 먼저 고치고, 관련 담당자 모두가 리뷰합니다.
- **AWS 리소스는 Terraform으로만.** 콘솔에서 만든 것은 코드로 옮기거나 지웁니다. 에이전트는 사람의 명시적 지시 없이 `terraform apply`·`destroy`, AWS 생성·삭제 명령을 실행하지 않습니다.
- **개인정보 금지.** 실제 영수증 사진·카드번호·이름·전화번호를 로그, 테스트 데이터, 커밋, 이슈에 넣지 않습니다. 샘플은 `services/scripts/make_sample_receipt.py`로 만든 합성 이미지만 씁니다.
- **비밀값 금지.** 비밀번호·토큰·키·임시 비밀번호는 어디에도 적지 않습니다. `.env`, `*.local.json`은 git에 올리지 않습니다.
- **개발자 로그인은 로컬 전용.** `RF_DEV_LOGIN`·`RF_AUTH_MODE=dev`와 화면의 "개발자 모드"는 실제 배포 설정·이미지에 넣지 않습니다. 로컬 컨테이너 검증의 `AUTH=dev` 이미지는 로컬에서만 사용하며 배포·ECR 업로드에 재사용하지 않습니다. 단, 로컬 개발자 모드의 **관리자 화면에서 만들거나 고치거나 지운 계정은 실제 공용 Cognito 계정**입니다(서버가 본인 AWS 자격 증명으로 처리). 웹 계정 발급·변경·삭제는 웹 관리자만 합니다.
- **AI는 제출하지 않습니다.** 제출·승인은 항상 사람이 버튼으로 합니다.
- `main`에 직접 푸시하지 않습니다.

## 지켜야 할 서비스 결정

- 범위: 기획서 Must, **카드 결제 영수증만** (현금·계좌이체·취소/반품 제외).
- 지출 분류 10개: 식사·간식비 · 접대·선물비 · 교통·출장비 · 우편·배송비 · 사무용품·소모품비 · 도서·교육비 · 행사·복리후생비 · 통신·구독비 · 광고·홍보비 · 기타 업무비 (`services/common/.../domain.py`).
- 역할 3개: 직원(employee) · 검수 담당자(reviewer) · 관리자(admin). 관리자는 계정·증빙 관리만 하고 작성·검수 화면이 없습니다.
- 프로필(이름·사번·부서·직급·역할)은 Cognito에 있고 관리자만 바꿉니다. 본인은 비밀번호만 바꿉니다.
  - 부서 7개(경영지원·재무회계·기획·영업·마케팅·개발·감사부, 영문 3글자 코드), 직급 6개(사원~부장) — 목록에서만 고릅니다 (`services/common/.../org.py`).
  - 검수 담당자는 재무회계부만, 관리자는 부서 없음.
  - 사번 = 부서 코드(관리자 `ADM`) + 만든 연도 + 순번 (`DEV2026001`), 만든 뒤 바뀌지 않습니다.
- 카드번호는 영수증에 찍힌 그대로 저장합니다(가림 없음). 거래 일시는 분까지.
- 사진을 다시 찍으면 다른 영수증일 수 있으므로 칸·목적·분류·대화를 모두 비웁니다 (부서·처리 이력은 유지).
- 검수 순서는 먼저 제출된 순, 주의·오류는 강조만 합니다.
- 영수증 사진은 S3에서 90일 뒤 자동 삭제됩니다.

## 담당과 경계

| 영역 | 경로 | 주 담당 | GitHub |
|---|---|---|---|
| 웹 화면·사용자 흐름 | `web/` | ① 장차희 | @CHAHEE03 |
| AI·데이터 처리 | `services/ocr-worker`, `services/chat-service`, `services/preprocess-service` | ② 김태희 | @igwi292 |
| 백엔드·DB | `services/api-service`, `services/common` | ③ 김수빈 | @bb2002 |
| AWS·배포 | `infra/`, `deploy/`, `.github/` | ④ 박준영 | @nemm3623 |

- 담당 영역 밖 파일을 고치는 PR은 그 영역 담당자를 리뷰어로 지정합니다. `.github/CODEOWNERS`가 경로별 담당자에게 리뷰를 자동 요청합니다.
- 작업 범위 밖 파일은 고치지 않습니다. 필요하면 PR 설명에 적고 담당자와 이야기합니다.

## 브랜치·PR·검사

- **새 작업 시작 순서:** `git status`로 현재 브랜치와 미커밋 변경을 확인 → 작업 트리가 깨끗하면 `git switch main` → `git pull --ff-only origin main`으로 최신 코드 받기 → `git switch -c <영역>/<짧은-설명>`으로 작업 브랜치 생성 → 수정 시작. 최신 코드 받기에 실패하면 원인을 해결한 뒤 진행합니다.
- **기존 작업 보호:** 미커밋 변경이나 아직 머지하지 않은 작업이 있으면 임의로 덮어쓰기·삭제·초기화·강제 전환하지 않습니다. 기존 작업을 확인하고 필요한 커밋·임시 보관 방법을 작업자와 정한 뒤 진행합니다. 기존 작업을 이어가는 경우에는 해당 브랜치를 사용하며, 최신 `main` 반영 전에도 변경 상태를 확인합니다. 같은 폴더에서 다른 사람이나 에이전트가 작업 중이면 브랜치를 전환하지 않습니다.
- `<영역>/<짧은-설명>` 브랜치 → PR → 다른 영역 담당 1명 리뷰 → 머지 (squash).
- 커밋 메시지 접두사: `[web]`, `[ai]`, `[api]`, `[infra]`, `[docs]`.
- PR 전 로컬에서 통과시키고, 필수 CI 검사(services, web, terraform, images)가 통과해야 머지합니다.
  - 백엔드: `cd services && uv run ruff format --check . && uv run ruff check . && uv run pytest`
  - 웹: `cd web && node --test tests/*.test.mjs && npm run build`
  - 인프라: `terraform fmt -recursive infra/terraform`, `validate`, `plan`
- Terraform "No changes"는 코드와 실제 리소스가 일치한다는 뜻일 뿐, 비용이 안 나간다는 뜻이 아닙니다.

## 협업 진행

- **일 나누기:** 작업은 GitHub 이슈 하나로 시작하고, 이슈에 담당자를 지정한 뒤 브랜치를 만듭니다(브랜치 하나 = 이슈 하나 = PR 하나). 여러 영역에 걸친 일은 영역별 이슈로 나누고, 규약(`contract.md`)을 먼저 고치는 PR을 앞에 둡니다.
- **PR 설명:** `.github/pull_request_template.md` 항목(요약, 영역, 규약 변경, 검사 결과, 화면 확인, AWS·비용 영향, 워커 재시작 필요)을 채웁니다. 화면 캡처는 합성 데이터로만 찍습니다.
- **리뷰:** 다른 영역 담당 1명 이상. 영역 밖 파일을 고쳤으면 그 영역 담당자도 넣습니다. 리뷰 요청을 받으면 다음 작업일 안에 승인·수정 요청·질문 중 하나로 답합니다.
- **머지:** 승인과 필수 CI 통과 후 PR 작성자가 squash 머지하고 브랜치를 지웁니다. `main` 직접 푸시는 하지 않습니다.
- **최신 `main` 반영:** PR이 `main`과 충돌하면 작성자가 자기 브랜치에 `git merge origin/main`으로 반영하고 충돌을 풉니다. 이미 푸시한 브랜치는 rebase·강제 푸시하지 않습니다. 남의 영역 충돌은 그 담당자에게 물어 보고 풉니다.
- **규약 변경:** `contract.md`를 바꾸는 PR은 바뀌는 쪽 서비스 담당과 쓰는 쪽(웹 등) 담당이 모두 승인해야 머지합니다. 같은 PR에서 웹 타입(`web/src/api.ts`)·테스트·문서를 함께 맞춥니다.
- **의존성 추가:** `uv add`·`npm install`로 추가하고 잠금 파일(`services/uv.lock`, `web/package-lock.json`)을 같은 PR에 커밋합니다. 머지 후 팀 대화방에 알려 각자 `uv sync --frozen`·`npm ci`를 하게 합니다.
- **완료 기준:** 로컬 검사·CI 통과, 새 동작의 테스트, 바뀐 내용의 문서 갱신(같은 PR), 화면 변경이면 375·1440px 확인과 캡처, 공용 AWS 데이터·워커에 영향이 있으면 팀 공지.
- **AI 에이전트:** Claude Code는 `CLAUDE.md`(= 이 파일), Codex는 이 파일을 읽습니다. 다른 도구를 쓰면 이 파일을 규칙으로 읽도록 설정합니다. 에이전트의 변경도 사람과 같은 PR·리뷰를 거치며, 에이전트에게 맡긴 사람이 결과를 확인할 책임이 있습니다.

## 코드 규칙

- Python 3.13, uv 워크스페이스(`services/`). 설정은 `RF_*` 환경 변수(`services/.env.example`)로만 받습니다.
- AWS 클라이언트는 `receiptflow_common.aws`를 통해 만듭니다(테스트에서 moto로 교체됨). `uv run pytest`는 실제 AWS에 쓰지 않습니다.
- 새 API는 `docs/contract.md`에 먼저 적고, `services/tests/`에 테스트를 추가합니다. 파일 이름은 영역 접두사: `test_api_*`(③), `test_chat_*`·`test_ocr_*`·`test_preprocess_*`(②), `test_common_*`(③), 여러 서비스를 거치는 흐름은 `test_flow.py`. 공통 도우미는 `tests/helpers.py`.
- 사용자에게 보이는 문구는 한국어(존댓말), 코드·주석·커밋은 영어 또는 한국어.
- 웹 화면은 AWS 콘솔 느낌(로고 아래 막대·왼쪽 메뉴·요약 줄·표)을 유지합니다. 색·간격은 `web/src/styles/base.css`의 변수를 쓰고, 스타일은 영역별 파일(`styles/receipt.css`, `review.css`, `admin.css` …)에 둡니다.

## AWS 사용 규칙 (예산 $200, 11/14까지)

- 팀원 IAM 사용자는 `AdministratorAccess`에 금지 정책이 덧붙어 있습니다 (`infra/terraform/admin/guard.tf`). CLI·로컬 개발은 그대로 되고, 다음은 막힙니다:
  공유 리소스(테이블·버킷·큐·사용자 풀·이미지 저장소) 삭제, 서울 밖에 비용 드는 리소스 생성, `t3`/`t3a`/`t4g` 외 인스턴스, IAM 변경(인프라 담당·리드 제외), 다른 사람의 로그인·키 변경.
  공유 리소스를 정말 지워야 하면 팀에 먼저 알리고, IAM 관리자(박준영·장차희)가 `guard_enabled=false`로 apply → 작업 → 같은 날 되돌립니다. `admin` 스택(IAM)은 IAM 관리자만 apply 할 수 있습니다. 루트 계정은 CLI·Terraform에 쓰지 않습니다.
- 개발은 로컬에서 하고(공유 S3·SQS·DynamoDB·Cognito 사용), 배포는 EKS로 합니다(`infra/terraform/eks`, `deploy/`).
- EKS·EC2·ALB·NAT처럼 시간당 비용이 드는 리소스는 배포·시연할 때만 팀 합의 후 만들고, 끝나면 같은 날 지웁니다. 주간 회의 첫 안건은 월요일 비용 메일의 **이번 달 금액**입니다.
- 공유 리소스를 같이 쓰므로, 다른 사람이 올린 영수증·계정을 지우거나 바꾸는 작업(`seed_*`·`clear_*` 스크립트 포함)은 팀 단체 대화방에 미리 알립니다.
- Terraform 상태 파일은 git에 없습니다. 같은 스택의 `plan`·`apply`는 한 사람만 동시에 실행합니다.
- 로컬 `ocr-worker`는 합의된 동일 OCR·공통 코드 버전과 `RF_AI_MODE=bedrock`, 동일 `RF_EXTRACT_MODEL` 설정으로 각자 실행할 수 있습니다. 공용 큐의 다른 팀원 사진도 처리하므로 수정 중인 OCR·공통 코드나 mock 워커를 공용 큐에 연결하지 않습니다. 수정·모델 변경·검증·재시작 절차는 [docs/worker.md](docs/worker.md)를 따릅니다. 부하 테스트는 실제 큐와 분리한 mock 환경에서 진행합니다(Bedrock 비용 방지).
- 비용은 AWS Budgets로 봅니다(조직 정책으로 Cost Explorer는 막혀 있음). 매주 월요일 비용 메일과 $50·$100·$150 알림이 옵니다 (`infra/terraform/ops`).
