# 로컬 개발 시작하기 (Windows·Git Bash / macOS)

처음 저장소를 받은 팀원이 도구 설치 → AWS 로그인 → 환경 파일 생성 → 서버 실행 → 웹 접속까지 따라가는 안내입니다. 일반 로컬 개발은 Docker·Terraform·EKS 없이 실행합니다. DB를 PC에 설치하지 않으며, 팀 공용 **DynamoDB·S3·SQS·Cognito·Bedrock**을 사용합니다.

**Mac 사용자:** 1단계 도구 설치만 아래 [macOS](#macos) 절을 따르고, 2단계부터는 같습니다. 이 문서의 `bash` 명령은 Mac 기본 **터미널**(zsh)에서 그대로 실행합니다. "Git Bash"라고 적힌 곳은 Mac에서는 터미널로 읽으면 됩니다.

## 1. 처음 한 번: 도구 설치

### Windows

| 도구 | 설치·확인 |
|---|---|
| Git for Windows | [공식 설치 파일](https://git-scm.com/downloads/win)로 설치합니다. 설치 후 **Git Bash**를 엽니다. GitHub Desktop은 선택입니다. |
| Node.js 22 | [공식 22.x 다운로드](https://nodejs.org/en/download/archive/v22)에서 Windows용 설치 파일을 선택합니다. npm도 함께 설치합니다. CI와 맞추려면 22.x를 사용합니다. |
| uv | [공식 Windows 설치 안내](https://docs.astral.sh/uv/getting-started/installation/)를 따릅니다. 아래 PowerShell 명령으로도 설치할 수 있습니다. |
| Python 3.13 | uv 설치 후 아래 `uv python install 3.13`으로 설치합니다. 프로젝트는 3.13만 지원합니다. |
| AWS CLI v2 | [공식 Windows 설치 안내](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html)를 따릅니다. `aws login`을 지원하는 버전을 사용합니다. |

uv를 설치할 때만 **PowerShell**에서 실행합니다.

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

설치 후 터미널을 모두 닫고 새 **Git Bash**를 엽니다. 이후 명령은 별도 표시가 없으면 Git Bash용입니다. PowerShell이나 WSL과 섞어 쓰지 않습니다.

```bash
git --version
node --version
npm --version
uv --version
aws --version
uv python install 3.13
```

각 명령이 버전을 출력하고 Python 설치가 완료되면 다음으로 진행합니다. `command not found`면 설치 및 PATH를 확인하고 Git Bash를 다시 엽니다. Python을 별도로 활성화할 필요는 없으며 이후 `uv run`이 프로젝트 가상환경을 사용합니다.

### macOS

[Homebrew](https://brew.sh)를 먼저 설치한 뒤 **터미널**에서 실행합니다. 개발자 도구(git)·Node.js 22·AWS CLI v2·uv·Python 3.13을 설치합니다.

```bash
xcode-select --install
brew install node@22 awscli
curl -LsSf https://astral.sh/uv/install.sh | sh
```

`node@22`는 Homebrew가 PATH에 자동으로 넣지 않으므로 한 번 추가합니다(Intel Mac은 `/opt/homebrew` 대신 `/usr/local`).

```bash
echo 'export PATH="/opt/homebrew/opt/node@22/bin:$PATH"' >> ~/.zshrc
```

터미널을 닫았다가 새로 연 뒤 Windows와 같은 확인 명령을 실행합니다.

```bash
git --version
node --version
npm --version
uv --version
aws --version
uv python install 3.13
```

`node --version`이 `v22.`로 시작하고 `aws --version`이 `aws-cli/2.`로 시작하면 됩니다. 합성 영수증 스크립트는 Mac 기본 한글 글꼴(Apple SD 산돌고딕)을 자동으로 사용합니다. 배포하는 사람만 Docker Desktop for Mac, kubectl, helm(`brew install kubectl helm`)을 추가로 설치합니다.

## 2. 처음 한 번: 저장소 받기

팀 저장소는 GitHub 조직 `aws-cloud-team4`의 `receipt-flow`입니다. 코드를 올리려면 조직 초대(메일 또는 GitHub 알림)를 먼저 수락해야 합니다. 다운로드할 상위 폴더에서 실행합니다.

```bash
git clone https://github.com/aws-cloud-team4/receipt-flow.git
cd receipt-flow
git status
```

GitHub 인증 창이 나오면 본인 GitHub 계정으로 로그인합니다. 이미 받은 폴더가 있으면 다시 clone하지 않고 그 폴더를 사용합니다.

이후 **프로젝트 루트**는 `README.md`, `AGENTS.md`, `services/`, `web/`이 있는 폴더를 뜻합니다. 폴더명은 PC마다 달라도 됩니다. 예를 들어 `C:\AWS`는 Git Bash에서 `/c/AWS`입니다. 경로에 공백이 있으면 `cd "경로"`처럼 따옴표로 감쌉니다.

먼저 [AGENTS.md](../AGENTS.md)의 작업 규칙을 읽습니다. 새 기능·수정을 시작할 때는 [매일 작업 시작](#7-매일-작업-시작) 순서로 최신 코드와 작업 브랜치를 준비합니다.

## 3. 처음 한 번 및 세션 만료 시: AWS 로그인

**GitHub 계정, AWS IAM 계정, 웹 서비스 계정은 서로 다릅니다.** GitHub는 소스 코드, AWS IAM은 개발 서버의 AWS 접근, 웹 서비스 계정(Cognito)은 영수증 화면 로그인용입니다.

본인 IAM 계정의 로그인 정보는 IAM 관리자에게 받습니다. 첫 콘솔 로그인에서 비밀번호 변경·MFA 설정을 마친 뒤 실행합니다. 프로필 이름 `team-admin`은 팀 공통이지만 로그인하는 사람은 각자 본인입니다.

```bash
aws login --profile team-admin
aws configure set region ap-northeast-2 --profile team-admin
aws sts get-caller-identity --profile team-admin
```

브라우저에서 **본인 IAM 사용자**로 로그인하고 마지막 허용까지 완료합니다. 마지막 명령의 `Arn`이 `...:user/<본인>`이고 계정이 `431777499129`인지 확인합니다. `...:root`라면 진행하지 말고 IAM 사용자로 다시 로그인합니다. 비밀번호·키·토큰을 채팅이나 저장소에 올리지 않습니다. 자세한 권한 안내는 [aws.md](aws.md#처음-설정-팀원)를 참고합니다.

## 4. 처음 한 번: 의존성·환경 파일 준비

프로젝트 루트에서 실행합니다.

```bash
cd services
uv sync --frozen
uv run python scripts/make_env.py --dev-login
cd ../web
npm ci
cd ..
```

- `uv sync --frozen`: 저장소의 잠금 파일 기준으로 백엔드 의존성을 설치합니다.
- `make_env.py`: 본인 AWS 로그인으로 기존 공용 리소스를 **조회**해 `services/.env`와 `web/.env.local`을 생성합니다. AWS 리소스를 생성하거나 변경하지 않습니다.
- `--dev-login`: 로컬 로그인 화면의 개발자 모드를 허용합니다. 기본 Cognito 로그인도 유지됩니다.
- `npm ci`: 잠금 파일 기준으로 웹 의존성을 설치합니다.

환경 파일 두 개가 생겼고 모든 명령이 오류 없이 끝났으면 준비 완료입니다. `.env`·AWS 인증정보를 다른 팀원에게 복사받거나 git에 추가하지 않습니다. Terraform 상태 파일도 필요하지 않습니다.

### 설치 확인: 자동 테스트

서버를 켜기 전에 설치가 맞는지 자동 테스트로 확인합니다. AWS를 흉내 내는 moto로 돌기 때문에 공용 데이터를 바꾸지 않고 비용도 없습니다. 프로젝트 루트에서 실행합니다.

```bash
cd services && uv run pytest -q
```

```bash
cd web && node --test tests/*.test.mjs && npm run build
```

백엔드는 `… passed`, 웹은 `fail 0`과 `built in`이 나오면 됩니다. 실패하면 Python 3.13·Node 22 설치와 `uv sync --frozen`·`npm ci` 결과를 다시 확인합니다.

### 환경 파일 다시 만들기

기존 환경 파일은 자동으로 덮어쓰지 않습니다. 공유 리소스 설정 변경 등으로 재생성이 필요하면 서버를 종료하고 `services/`에서 `uv run python scripts/make_env.py --dev-login --force`를 실행합니다. 이전 파일은 `.bak`으로 보관되므로 이 파일도 공유하지 않습니다. 개인 설정이 있었다면 백업과 비교해 반영합니다.

## 5. 실행: 각자 터미널 2개

Git Bash 창을 두 개 열고 **각각 프로젝트 루트로 이동**합니다. 아래 서버는 실행 중 터미널을 계속 사용하므로 서로 다른 창에서 실행합니다.

### 터미널 A — 백엔드 3개와 OCR 워커

```bash
cd services
bash scripts/dev.sh
```

`Uvicorn running on ...:8000`, `:8001`, `:8002`와 `ocr-worker started (ai_mode=bedrock, model=global.anthropic.claude-sonnet-5-5)` 메시지를 확인합니다. [워커 설정·코드 확인](worker.md#실행-전-확인)도 먼저 따릅니다.

| 포트 | 서비스 | 용도 |
|---|---|---|
| 8000 | API | 로그인 후 사용자·증빙·검수·관리자 기능 |
| 8001 | Chat | AI 대화 |
| 8002 | Preprocess | 사진 테두리 검출·보정 |
| 5173 | Web | 브라우저 화면 (터미널 B) |

### 터미널 B — 웹

```bash
cd web
npm run dev -- --port 5173 --strictPort
```

`Local: http://localhost:5173/`가 표시되면 브라우저에서 **[http://localhost:5173](http://localhost:5173)**을 엽니다. 백엔드가 켜져 있어야 로그인 이후 기능이 작동합니다. `--strictPort`는 포트가 사용 중이면 다른 주소로 바꾸지 않고 오류를 표시하도록 합니다.

### 각자 워커를 실행하는 기준

터미널 A의 OCR 워커는 내 사진만이 아니라 **공용 큐의 모든 팀원 사진**을 처리합니다. 최신 `main` 코드·실제 Bedrock 설정일 때만 켜고, OCR·공통 코드를 고치는 중이거나 화면·API만 볼 때는 `WORKER=0 bash scripts/dev.sh`로 워커를 뺍니다. 확인 방법과 수정 절차는 [OCR 워커 운영](worker.md)에 있습니다.

## 6. 웹 로그인·첫 확인

로컬에서는 다음 중 하나로 로그인합니다.

- **개발자 모드:** 로그인 화면 아래 개발자 모드를 열고 테스트 계정을 선택합니다. 테스트 관리자(오태민)로 들어간 관리 화면에서 계정을 만들거나 지우면 **실제 공용 Cognito 계정**이 바뀌므로 계정 관리 화면은 쓰지 않습니다. 4단계의 `--dev-login` 설정이 필요합니다. 비밀번호 없이 역할별 화면을 확인할 수 있지만, 데이터는 여전히 공용 AWS에 저장됩니다.
- **Cognito 계정:** 웹 관리자가 발급한 본인 계정으로 로그인합니다. AWS 콘솔 비밀번호를 입력하는 화면이 아닙니다. 발급 순서는 다음과 같습니다.
  1. 팀 대화방에서 웹 관리자에게 이메일·이름·부서·직급·역할을 알려 요청합니다.
  2. 관리자가 관리 화면(계정 관리 → 만들기)에서 계정을 만들면 임시 비밀번호가 **한 번만** 표시됩니다.
  3. 관리자는 임시 비밀번호를 본인에게만 따로 전달합니다. 단체 대화방·이슈·커밋에 올리지 않습니다.
  4. 첫 로그인에서 임시 비밀번호를 입력하고 새 비밀번호를 정합니다. 잊으면 관리자가 임시 비밀번호를 다시 발급합니다.
  팀원이 각자 초기 계정 생성 스크립트(`seed_users.py`)를 실행하지 않습니다.

관리자는 계정·증빙 관리 화면만 있고 작성·검수 화면이 없습니다. 직원과 검수 담당자는 각자 역할에 맞는 화면을 확인합니다.

사진 테스트에는 실제 개인정보가 든 영수증 대신 저장소에 있는 합성 이미지 `docs/samples/sample-receipt.jpg`를 사용합니다. 다른 합성 영수증이 필요하면 `services/`에서 `uv run --with pillow python scripts/make_sample_receipt.py <저장할 경로>`로 만듭니다.

합성 이미지를 선택해 사진 업로드 → 테두리 확인·보정 → 분석 결과 표시를 확인합니다. 제출·승인 검증은 사람이 직접 버튼을 누릅니다. 다른 사람의 증빙·계정을 수정하거나 삭제하지 않습니다.

## 7. 매일 작업 시작

새 작업은 프로젝트 루트에서 아래 순서로 진행합니다. **미커밋 변경·진행 중인 브랜치·같은 폴더에서 실행 중인 에이전트가 있으면 먼저 확인**하고, 임의로 초기화하거나 브랜치를 전환하지 않습니다. 기존 작업을 이어갈 때는 기존 브랜치를 사용합니다.

작업 트리가 깨끗하고 새 작업을 시작하는 경우:

```bash
git status
git switch main
git pull --ff-only origin main
```

다음으로 `git switch -c <영역>/<짧은-설명>`을 실행합니다. 예를 들어 웹 작업은 `git switch -c web/receipt-help`처럼 **이번 작업에 맞는 새 이름**을 사용합니다. `<...>`를 그대로 입력하지 않습니다. Pull이 실패하면 해결한 뒤 수정합니다.

의존성 변경도 반영합니다. 서버가 실행 중이라면 먼저 종료합니다.

```bash
cd services
uv sync --frozen
cd ../web
npm ci
cd ..
aws sts get-caller-identity --profile team-admin
```

AWS 세션이 만료됐으면 `aws login --profile team-admin`을 다시 실행하고 5단계대로 서버를 켭니다. 환경 파일은 매일 새로 만들지 않아도 됩니다. 작업 후 담당 영역 검사 → 커밋·Push → PR → 다른 영역 담당 리뷰 → CI 통과 → squash 머지 순서를 따릅니다.

### 작업을 PR로 올리기

`main`은 보호되어 있어 직접 푸시할 수 없습니다. 작은 수정도 브랜치 → PR → 리뷰 → 머지를 거칩니다. 규칙은 [AGENTS.md](../AGENTS.md#협업-진행)에 있습니다.

1. 담당 영역 검사를 통과시킵니다(웹: `cd web && node --test tests/*.test.mjs && npm run build`, 백엔드: `cd services && uv run ruff format --check . && uv run ruff check . && uv run pytest`).
2. 커밋하고 팀 저장소에 올립니다. 커밋 메시지 접두사는 `[web]`·`[ai]`·`[api]`·`[infra]`·`[docs]`입니다. 이때 팀 저장소에 브랜치가 생기지만 PR은 아직 없습니다.

```bash
git add -A
git commit -m "[web] 제출 버튼 문구 수정"
git push -u origin web/submit-button-text
```

3. PR을 엽니다. GitHub 저장소 화면 위쪽의 **Compare & pull request**를 누르고(GitHub CLI를 설치했다면 `gh pr create --base main --fill`도 됨), PR 템플릿 항목(요약·영역·검사 결과·화면 확인·AWS 영향·워커 재시작)을 채웁니다.
4. CI 7개가 자동으로 돌고, `.github/CODEOWNERS`에 따라 담당자에게 리뷰가 요청됩니다. 수정 요청을 받으면 **같은 브랜치**에서 고쳐 다시 푸시합니다(같은 PR에 추가됨, 새 PR 금지).
5. CI 통과와 승인 1명이 되면 작성자가 PR 화면에서 **Squash and merge**를 누릅니다. 팀 저장소의 브랜치는 자동으로 지워집니다.
6. 내 PC를 최신 `main`으로 맞추고 끝난 브랜치를 지웁니다.

```bash
git switch main
git pull --ff-only origin main
git branch -d web/submit-button-text
```

혼자 오래 걸리는 큰 작업은 `<GitHub아이디>/dev` 브랜치를 쓰며, 작업을 시작할 때마다 `git fetch origin && git merge origin/main`으로 팀 변경을 섞습니다(AGENTS.md "개인 큰 작업은 dev").

## 8. 종료·재시작

각 서버 터미널에서 **Ctrl+C**를 누릅니다. 가능하면 진행 중 분석이 끝난 뒤 워커를 종료합니다. 마지막 워커를 끄면 팀에 분석이 대기하게 됨을 알립니다. 서버 코드를 수정하거나 환경 파일을 변경했으면 해당 서버를 종료한 뒤 같은 명령으로 다시 켭니다. 웹 소스 변경은 개발 서버가 보통 자동 반영하지만 환경 파일 변경은 재시작이 필요합니다.

창을 닫았는데도 포트가 남았다면 새 서버를 반복해서 켜지 말고 기존 프로세스를 확인합니다. 모든 Python·Node 프로세스를 한꺼번에 종료하지 않습니다. 9단계의 포트 확인으로 우리 서버인지 확인한 프로세스만 종료합니다.

## 9. 자주 막히는 곳

| 증상 | 확인·해결 |
|---|---|
| `command not found` | 도구 설치와 PATH를 확인하고 Git Bash를 다시 엽니다. |
| GitHub `Repository not found`·인증 오류 | 저장소 주소, 협업자 초대 수락 여부, 로그인한 GitHub 계정을 확인합니다. |
| `aws login`이 없는 명령이라고 표시 | AWS CLI v2를 공식 설치 안내에 따라 업데이트합니다. |
| `LoginRefreshRequired`·`Your session has expired` | `aws login --profile team-admin` 후 STS 조회를 재확인합니다. 계속 실패하면 해당 로컬 서버를 재시작합니다. |
| 환경 생성 시 `AccessDenied`·리소스를 찾지 못함 | 본인 IAM 사용자, 계정, 서울 리전, 팀 공유 리소스 접근 권한을 확인합니다. 임의로 리소스를 만들지 말고 인프라 담당자에게 오류를 전달합니다. |
| 환경 파일이 이미 있다고 표시 | 파일이 있으면 재사용합니다. 의도적으로 갱신할 때만 4단계의 `--force`를 사용합니다. |
| Python 버전 오류 | `uv python install 3.13` 후 `services/`에서 `uv sync --frozen`을 다시 실행합니다. |
| `address already in use`·5173 포트 오류 | 같은 서버가 이미 켜져 있는지 확인합니다. 아래 명령으로 포트 점유 프로세스를 식별합니다. |
| 웹이 안 열림 | 터미널 B가 실행 중인지, 출력 주소가 `http://localhost:5173`인지 확인합니다. 로컬 개발에 CloudFront 주소를 사용하지 않습니다. |
| 로그인 후 화면이 안 넘어감·API 연결 오류 | 터미널 A의 3개 서버와 AWS 세션을 확인합니다. GitHub 로그인·IAM 로그인·웹 계정을 혼동하지 않습니다. |
| 개발자 모드가 안 보이거나 거부됨 | `services/.env`의 `RF_DEV_LOGIN=true`를 확인하고 API를 재시작합니다. 개발자 모드는 로컬 전용입니다. |
| 보정 후 분석이 계속 대기함 | 내 워커의 시작 로그·AWS 세션·큐 설정을 확인합니다. 같은 승인 코드·실제 모델 설정으로 워커를 켤 수 있습니다. 다른 워커가 남아 있으면 처리되며 모든 워커가 꺼져 있으면 대기합니다. [점검 방법](worker.md#분석이-대기하거나-실패할-때) 참고. |
| 브라우저 API 오류·서버 오류 | 오류 시각, 서비스 이름, 오류 문구를 담당자에게 전달합니다. 사진·비밀번호·토큰·환경 파일 전체를 공유하지 않습니다. |

Mac에서는 터미널에서 `lsof -nP -iTCP -sTCP:LISTEN | grep -E ':(5173|8000|8001|8002) '`로 포트를 쓰는 프로세스와 PID를 확인합니다. Windows는 아래 명령만 **PowerShell**에서 실행하면 포트와 PID를 확인할 수 있습니다.

```powershell
Get-NetTCPConnection -State Listen -LocalPort 5173,8000,8001,8002 -ErrorAction SilentlyContinue |
  Select-Object LocalAddress,LocalPort,OwningProcess
```

표의 `OwningProcess` 숫자로 `Get-Process -Id <PID>`를 조회합니다. 예를 들어 PID가 1234면 `Get-Process -Id 1234`입니다. 확인한 우리 서버는 원래 터미널에서 Ctrl+C로 종료하는 것을 우선합니다.

로컬 실행 문제는 이 문서, 서비스 내부 구조는 [backend.md](backend.md)·[ui.md](ui.md)·[ai.md](ai.md), 실제 배포는 [deploy/README.md](../deploy/README.md)를 참고합니다.
