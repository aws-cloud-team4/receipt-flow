# 현재 AI 모델과 평가

## 사용 모델

| 용도 | 모델 | 환경 변수·기본값 |
|---|---|---|
| 영수증 이미지 분석 | Claude Sonnet 5.5 | `RF_EXTRACT_MODEL=global.anthropic.claude-sonnet-5-5` |
| 챗봇 | Claude Haiku 5.5 | `RF_CHAT_MODEL=global.anthropic.claude-haiku-5-5` |
| 자동 테스트·부하 테스트 | 모델 호출 없음 | `RF_AI_MODE=mock` (moto 또는 별도 테스트 리소스, 공용 큐 연결 금지) |

Bedrock의 글로벌 추론 프로필을 사용합니다. 기본 설정은 `services/common/src/receiptflow_common/config.py`, 실제 로컬 설정은 git에 없는 `services/.env`, 배포 설정은 `deploy/k8s/config.yaml`에서 관리합니다. 이미지 추출 프롬프트 버전은 `services/ocr-worker/src/ocr_worker/extractor.py`의 `PROMPT_VERSION`입니다.

## 최신 평가 수치

모델 **Sonnet 5.5** (`global.anthropic.claude-sonnet-5-5`). 각 세트의 마지막 `results.json` 집계만 유지합니다. 원본 사진·정답·모델 출력은 문서에 넣지 않습니다.

| 평가 대상 | 측정일 | 장수 | 핵심 3필드 모두 정답 | 전체 비교 필드 정확도 | 오류 | 지연 중앙값 | 장당 비용 추정 |
|---|---|---|---|---|---|---|---|
| 합성 업무 지출 세트 (`work`) | 2026-11-09 | 18 | **100%** | **100%** | 0 | **4.0초** | **$0.01448** |
| 기본 합성 세트 (`set`) | 2026-11-09 | 12 | **100%** | **100%** | 0 | **3.2초** | **$0.01338** |
| 실제 영수증 (팀원 5 + 공개 데이터셋 18) | 2026-11-09 | 23 | 91.3% (21/23) | 96.5% (218/226) | 0 | 5.9초 (공개 18장) | — |

- 집계 출처: 각 세트 `results.json`의 해당 모델 `summary`. 결과 파일은 git에 포함하지 않으므로 새 팀원 PC에는 없습니다.
- 합성 세트 2개(11-09)는 `PROMPT_VERSION = "receipt-extract-v9"` 코드로 측정했습니다(`extractor.py`는 2026-10-23 이후 바뀌지 않음). 다만 결과 파일 자체에는 프롬프트 버전이 기록되지 않습니다. 합성 이미지는 스크립트가 만든 깨끗한 영수증이라 실제 촬영(구김·조명·기울기·흐림)보다 쉬우므로 100%를 실제 영수증 성능으로 해석하지 않습니다.
- 실제 영수증 23장(11-09, `receipt-extract-v9`): 팀원이 직접 찍은 카드 영수증 5장(카페 키오스크 2·우체국·버거·편의점, 55칸 모두 일치)과 공개 데이터셋 [HumynLabs/Korean_Receipts_Dataset](https://huggingface.co/datasets/HumynLabs/Korean_Receipts_Dataset)(CC BY 4.0)의 카드 영수증 18장(핵심 3필드 16/18, 전체 163/171). 공개 데이터셋에는 정답이 없어 Claude Code가 사진을 보고 정답지를 만들었고 애매한 칸은 비교에서 뺐습니다. 틀린 것: 상호명 판단 차이 2건(지점명만 찍힌 영수증, 백화점 안 식당), 라벨 없이 대괄호로만 찍힌 승인번호 누락, 제휴할인 영수증의 공급가액·부가세. 팀원 영수증은 개인정보가 있어 측정한 PC에만 두고 저장소·문서에 넣지 않습니다. 표본이 작아 실제 성능의 대략적인 기준으로만 봅니다.
- 핵심 3필드는 **상호명·거래 일시·총액**이며, 한 영수증에서 세 필드가 모두 맞아야 정답입니다. 전체 정확도는 평가 스크립트가 정답과 비교한 필드 기준입니다.
- 지연은 모델 요청 시간이며 큐 대기·사진 업로드·보정·대화 시간은 제외합니다. 비용은 평가 스크립트의 입력·출력 토큰 단가에 따른 추정치이며 실제 Bedrock 청구 금액이 아닙니다.
- 프롬프트·모델 변경 후에는 합성 데이터로 다시 평가하고 이 표를 교체합니다.
- 실제 모델을 호출하는 챗봇 시나리오 평가 세트는 아직 없습니다. `services/tests/test_chat_agent.py`는 모델을 흉내 내 도구·서버 규칙을 검사합니다.

## 합성 데이터로 평가하기

프로젝트 루트에서 실행합니다. 실제 Bedrock 비용이 발생하므로 일반 부하 테스트와 구분합니다.

```bash
cd services
uv run --with pillow python scripts/eval/make_work_set.py   # 합성 업무 지출 세트 18장 (scripts/eval/work/)
uv run python scripts/eval/compare_models.py --set work global.anthropic.claude-sonnet-5-5
uv run --with pillow python scripts/eval/make_eval_set.py   # 기본 합성 세트 12장 (scripts/eval/set/)
uv run python scripts/eval/compare_models.py --set set global.anthropic.claude-sonnet-5-5
```

결과는 각 세트 폴더의 `results.json`(`scripts/eval/work/`, `scripts/eval/set/`)에 저장됩니다. 새 결과를 반영할 때 모델 ID·프롬프트 버전·샘플 수·측정일·정확도·오류·지연·비용 추정 조건을 함께 적습니다. 과거 결과를 누적하거나 폐기한 모델 비교표를 남기지 않습니다.

개인정보가 담긴 실제 영수증을 새 테스트 데이터로 추가하지 않습니다. 합성 사진은 `services/scripts/make_sample_receipt.py`와 `scripts/eval/make_*.py`로 만듭니다.
