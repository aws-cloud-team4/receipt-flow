# 현재 AI 모델과 평가

## 사용 모델

| 용도 | 모델 | 환경 변수·기본값 |
|---|---|---|
| 영수증 이미지 분석 | Claude Sonnet 5.5 | `RF_EXTRACT_MODEL=global.anthropic.claude-sonnet-5-5` |
| 챗봇 | Claude Haiku 5.5 | `RF_CHAT_MODEL=global.anthropic.claude-haiku-5-5` |
| 자동 테스트·부하 테스트 | 모델 호출 없음 | `RF_AI_MODE=mock` (moto 또는 별도 테스트 리소스, 공용 큐 연결 금지) |

Bedrock의 글로벌 추론 프로필을 사용합니다. 기본 설정은 `services/common/src/receiptflow_common/config.py`, 실제 로컬 설정은 git에 없는 `services/.env`, 배포 설정은 `deploy/k8s/config.yaml`에서 관리합니다. 이미지 추출 프롬프트 버전은 `services/ocr-worker/src/ocr_worker/extractor.py`의 `PROMPT_VERSION`입니다.

## 최신 평가 수치

측정일 **2026-10-16**, 모델 **Sonnet 5.5**. 각 세트의 마지막 `results.json` 집계만 유지합니다. 원본 사진·정답·모델 출력은 문서에 넣지 않습니다.

| 평가 대상 | 장수 | 핵심 3필드 모두 정답 | 전체 비교 필드 정확도 | 오류 | 지연 중앙값 | 장당 비용 추정 |
|---|---|---|---|---|---|---|
| 실제 영수증 평가 집계 | 29 | **93.1%** | **98.3%** | 0 | **6.8초** | **$0.02072** |
| 합성 업무 지출 평가 | 18 | **100%** | **100%** | 0 | **4.0초** | **$0.01398** |

- 집계 출처: 각 세트 `results.json`의 해당 모델 `summary`. 결과 파일은 git에 포함하지 않으므로 새 팀원 PC에는 없습니다. 실제 영수증 세트는 개인정보가 있어 프로젝트 밖 개인 보관 위치로 옮겼고 팀에 공유하지 않습니다(다시 측정은 합성 세트로).
- 핵심 3필드는 **상호명·거래 일시·총액**이며, 한 영수증에서 세 필드가 모두 맞아야 정답입니다. 전체 정확도는 평가 스크립트가 정답과 비교한 필드 기준입니다.
- 지연은 모델 요청 시간이며 큐 대기·사진 업로드·보정·대화 시간은 제외합니다. 비용은 평가 스크립트의 입력·출력 토큰 단가에 따른 추정치이며 실제 Bedrock 청구 금액이 아닙니다.
- 결과에 프롬프트 버전이 기록돼 있지 않아 현재 프롬프트와 동일한 조건인지 확인되지 않았습니다. 이 수치를 현재 버전의 정확도 보장이나 모든 영수증의 성능으로 해석하지 않습니다. 프롬프트·모델 변경 후에는 합성 데이터로 다시 평가하고 이 표를 교체합니다.
- 실제 모델을 호출하는 챗봇 시나리오 평가 세트는 아직 없습니다. `services/tests/test_chat_agent.py`는 모델을 흉내 내 도구·서버 규칙을 검사합니다.

## 합성 데이터로 평가하기

프로젝트 루트에서 실행합니다. 실제 Bedrock 비용이 발생하므로 일반 부하 테스트와 구분합니다.

```bash
cd services
uv run --with pillow python scripts/eval/make_eval_set.py
uv run python scripts/eval/compare_models.py --set set global.anthropic.claude-sonnet-5-5
```

결과는 `services/scripts/eval/set/results.json`에 저장됩니다. 새 결과를 반영할 때 모델 ID·프롬프트 버전·샘플 수·측정일·정확도·오류·지연·비용 추정 조건을 함께 적습니다. 과거 결과를 누적하거나 폐기한 모델 비교표를 남기지 않습니다.

개인정보가 담긴 실제 영수증을 새 테스트 데이터로 추가하지 않습니다. 합성 사진은 `services/scripts/make_sample_receipt.py`와 `scripts/eval/make_*.py`로 만듭니다.
