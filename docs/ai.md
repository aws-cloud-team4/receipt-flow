# AI·데이터 처리 — ② 김태희

세 서비스가 AI·이미지를 맡습니다: **preprocess-service**(사진 보정), **ocr-worker**(영수증 → 필드 추출), **chat-service**(AI 어시스턴트).
모델은 Amazon Bedrock의 Claude (global 추론 프로필). 서버와 화면 사이 약속은 [contract.md](contract.md#chat-service-prefix-chat).

| 용도 | 설정 | 모델 | 왜 |
|---|---|---|---|
| 영수증 추출 | `RF_EXTRACT_MODEL` | `global.anthropic.claude-sonnet-5-5` | 영수증 이미지의 필드·품목 추출 — [현재 모델·평가 수치](model-eval.md) |
| AI 어시스턴트 | `RF_CHAT_MODEL` | `global.anthropic.claude-haiku-5-5` (thinking 끔) | 사진 없는 짧은 글, 빠르고 쌈 |
| 테스트·부하 | `RF_AI_MODE=mock` | 모델 없음 | 고정 결과(추출) + 대본 대화(dialog.py), Bedrock 호출 비용 없음. 공용 큐와 분리 |

`receiptflow_common/bedrock.py`의 `call_tool()`이 **도구 호출로 JSON을 강제**합니다. Claude 5세대는 `temperature`·도구 강제 호출을 받지 않으므로 모델 이름을 보고 요청을 자동으로 맞춥니다.

## 1. 사진 보정 (`preprocess-service`, OpenCV)

`correct.py` — 두 단계로 나눠 **사람이 사이에서 테두리를 고칠 수 있게** 했습니다.

1. `detect()` — 원본(브라우저가 긴 변 최대 3200px로 줄여 `raw/`에 올림)에서 영수증 네 모서리를 찾고, 흐림 점수(라플라시안 분산, 긴 변 1000px 기준)를 매김. 60 미만이면 `blurry`. 못 찾으면 가장자리에서 6% 안쪽 기본 틀.
2. 화면에서 사람이 모서리를 끌어 맞춤 (`CornerEditor`).
3. `apply()` — 원근 보정, 긴 변 2400px, JPEG 92 → `incoming/{id}.jpg` (이 저장이 분석을 시작시킴). 이상한 네 점은 `422 bad_corners`, `null`이면 원본 그대로.

원본은 `raw/`에 남아 검수자가 "원본"으로 비교합니다. 기기(브라우저) 쪽 보정은 하지 않습니다(결정).

## 2. 영수증 추출 (`ocr-worker`)

- `main.py` — SQS를 롱 폴링하고 S3 이벤트에서 `incoming/{id}.jpg`만 골라 처리합니다. `processing` → 추출 → 저장 → `done`. 시드 데이터(`seed` 표시)는 모델을 부르지 않고 메시지만 지웁니다. 로컬 실행 조건은 [worker.md](worker.md).
- 실패·재시도(AWS 오류 최대 3회, 영수증 아님·응답 오류는 즉시 `failed`, DLQ 적용 범위)는 [worker.md 실패 처리](worker.md#실패재시도와-중복-처리)에 있습니다.
- 추출 결과 저장 직전에 증빙을 다시 읽고 이미 입력된 필드는 채우지 않습니다. 다만 같은 순간의 수정·중복 메시지까지 원자적으로 보호하는 것은 아닙니다.
- `extractor.py` — **프롬프트·스키마·버전(`PROMPT_VERSION = "receipt-extract-v9"`)이 이 파일에 있음**. 바꾸면 버전을 올리고 평가를 다시 돌립니다.
  - 읽는 칸: 상호명, 사업자번호, 거래 일시(분까지), 공급가액, 부가세, 면세금액, 총액(할인 후 최종), 결제수단(카드사 이름으로 신용/체크 판단), 카드사, 카드번호(찍힌 그대로), 승인번호(앞자리 0 유지), 분류 제안, 품목 요약(`items` — 목적 추천에 사용), `uncertain_fields`, `is_receipt`.
  - 원칙: 보이는 것만 적고 추측하지 않음, 고객 개인정보(이름·전화·주소·계좌)는 어떤 칸에도 넣지 않음, 점포 코드·전화번호는 상호명에서 뺌.
  - 저장 시 `normalize_fields()`(공통)로 금액 정수화·일시 형식·분류 코드 변환, `run_checks()`로 검산·중복·같은 승인번호·심야·주말 점검.
- 측정: 증빙에 `model_usage {input_tokens, output_tokens, latency_ms}`와 `timings`를 저장합니다. 조건별 지연·비용 추정은 [모델 평가 문서](model-eval.md)를 참고합니다.

## 3. AI 어시스턴트 (`chat-service`)

`POST /chat/receipts/{id}/turn` 하나로 **사용자 말·화면 이벤트·추천 버튼**을 받고 SSE로 답합니다. 모델을 부를지 말지는 서버가 먼저 정합니다.

| 들어온 것 | 처리 | 모델 |
|---|---|---|
| `choice` (추천 버튼) | 목적·분류를 바로 저장, 다음 할 일 안내 | ❌ |
| `event: changes_requested` | "담당자 ○○님이 보완을 요청했어요: 사유" + 고칠 칸 버튼 | ❌ |
| `event: analysis_done` (결과 확인 전) | 정해진 문장 "영수증을 읽었어요. 내용이 맞는지 확인해 주세요." + 흐린 칸·검산 오류. 같은 턴에 목적·분류 추천을 **미리 만들어 숨겨 둠**(`pending_suggestions`) | ✅ (추천만) |
| 결과 카드 [맞아요]·[수정 완료] | `result_confirmed_at` 기록 → 주의 경고 한 문장 + "어떤 일로 쓰신 비용인가요?" + 숨겨 둔 추천 | ❌ |
| 결과 카드 [직접 수정] | 폼에서 고치라고 안내 + [수정 완료] | ❌ |
| 그 밖의 말 | `agent.run_turn()` — 도구를 쓰는 대화 (아래) | ✅ |

### 도구 (`agent.py`의 `TOOLS`, 실행은 `run_tool`)

| 도구 | 하는 일 | 서버가 막는 것 |
|---|---|---|
| `update_fields` | 사용자가 **말한 값**으로 칸 수정 (+ 처리 이력 `ai_edited`) | 부서·프로필 수정 불가, **같은 값이면 아무것도 안 바꾸고 화면 줄도 없음** |
| `set_category` | 분류 설정. `confirmed_by_user=false`면 추천(`ai_filled`) | 추천일 때는 "정했어요" 줄을 안 보냄(답에서 "…로 할까요?"로 물음) |
| `confirm_result` | AI가 읽은 결과를 사용자가 확인 | |
| `show_choices` | 다음 답에 버튼 (예/아니요 등) | 최대 8개 |
| `suggest_expense` | 목적·분류 쌍 추천 2~3개 → 버튼 | 유효한 분류만, 중복 제거 |
| `check_submission` | 빠진 필수 칸·오류 점검. 준비되면 화면에 최종 확인 카드 | **AI가 넣고 사람이 확인 안 한 분류(`unconfirmed`)가 있으면 준비 안 됨** |

### 모델에게 주는 것 (`context()`, 매 턴)

현재 증빙(칸·확인 필요·AI가 채운 칸·점검·분석 상태·결과 확인 여부), **거래 시간대**(서버가 계산: 새벽 0–5 · 아침 6–10 · 점심 11–13 · 오후 14–17 · 저녁 18–20 · 밤 21–23시), 품목 요약, 같은 가게 과거 증빙(최대 3건), 보완 요청 사유, 작성자 이름·부서·직급, 분류 코드 설명. 대화 기록은 최근 24개.

### 서버가 답을 검사하는 규칙 (모델을 믿지 않는 부분)

- 한 턴에 모델 호출 최대 4번(도구 → 결과 → …).
- **도구를 안 불렀는데 "바꿨어요/정했어요"라고 하면** 다시 쓰게 함 (`NUDGE_CLAIM`).
- **영어·생각 과정·"사용자가…" 같은 3인칭**이 섞이면 다시 쓰게 함 (`NUDGE_VOICE`), 화면에는 흘리지 않음.
- 화면 줄의 조사 "로/으로"는 `domain.ro()`가 받침을 보고 고름.
- AI는 **제출하지 않음**. 제출 버튼은 `check_submission`이 준비됐을 때 화면에 뜨고 사람이 누름.

### 지시문 (`agent.py`의 `SYSTEM`) 핵심

존댓말·최대 2문장·이모지 없음 / 한 번에 하나씩 / 사용자가 말한 값만 넣고 추천은 묻기 / 분류 원칙(식사·회의 다과는 식사·간식비, 외부 관계자는 접대·선물비 + 거래처 이름 묻기, 이름 없이 진행하면 보완 요청 가능성 한 번 안내, 임직원 복지는 행사·복리후생비 …) / 부서·가게 종류·시간대에 맞는 추천(야근·심야 목적은 19시 이후·밤·새벽에만) / 주말·심야 경고면 사유를 목적에 / 빠진 게 있으면 "준비됐다"고 말하지 않음.

### mock 대본 (`dialog.py`)

`RF_AI_MODE=mock`(격리된 테스트·부하): 정해진 질문(목적 → 분류 확인), 짧은 답은 그대로 목적으로, 과거 증빙·기본 예시로 추천 버튼. 공용 큐에 mock 워커를 연결하지 않습니다.

## 4. 평가·비용

| 무엇 | 어떻게 |
|---|---|
| 추출 정확도 | 합성 세트 생성 후 `cd services && uv run python scripts/eval/compare_models.py --set set global.anthropic.claude-sonnet-5-5` |
| 최신 수치·측정 조건 | [model-eval.md](model-eval.md)에서 관리. 현재 프롬프트와 평가 조건의 일치 여부 및 샘플 한계를 함께 확인 |
| 대화 품질 | `services/tests/test_chat_agent.py`(도구·서버 규칙, 모델 흉내) — 실제 모델로 도는 **대화 평가 세트는 아직 없음** (다음 할 일) |
| 비용 | 평가 문서의 조건별 토큰 비용 추정 참고. 실제 청구는 Budgets, 부하 테스트는 꼭 mock |

## 5. 고칠 때

OCR·공통 코드·모델을 변경하는 동안 공용 큐 워커는 종료하고 [워커 수정·검증·반영 절차](worker.md#ocr공통-코드나-모델을-수정할-때)를 따릅니다. mock·부하 테스트도 공용 큐와 분리합니다.

- 프롬프트를 바꾸면: `PROMPT_VERSION` 올리기 → 합성 평가 세트 재실행 → model-eval.md의 최신 결과 교체 → PR에 숫자.
- 새 도구·이벤트는 [contract.md](contract.md)에 먼저 적고 `services/tests/test_chat_*.py`에 테스트.
- 실제 영수증 사진·개인정보는 테스트·커밋·로그에 넣지 않습니다 (합성 이미지: `scripts/make_sample_receipt.py`, `scripts/eval/make_*.py`).
- 남은 개선점은 [architecture.md 남은 일](architecture.md#7-남은-일-우선순위)에서 관리합니다.
