## 요약
<!-- 무엇을 왜 바꿨는지 2~3줄. 관련 이슈: #번호 -->

## 영역
- [ ] ① 웹 `web/`
- [ ] ② AI `services/ocr-worker`·`chat-service`·`preprocess-service`
- [ ] ③ 백엔드 `services/api-service`·`common`
- [ ] ④ AWS·배포 `infra/`·`deploy/`·`.github/`
- [ ] 문서만

## 규약 변경
- [ ] 없음
- [ ] 있음 — `docs/contract.md`를 이 PR에서 고쳤고, 바뀌는 쪽·쓰는 쪽 담당자를 리뷰어로 넣었습니다

## 검사
<!-- 실행한 명령과 결과. 실행하지 않은 검사는 이유를 적습니다 -->
- [ ] `cd services && uv run ruff format --check . && uv run ruff check . && uv run pytest`
- [ ] `cd web && node --test tests/*.test.mjs && npm run build`
- [ ] `terraform fmt -recursive -check infra/terraform` / `validate` / `plan`

## 화면 확인
<!-- 화면 변경이면 375px·1440px 캡처(합성 데이터만). 없으면 "해당 없음" -->

## AWS·비용·공용 데이터
<!-- 새 리소스·권한, apply 필요 여부, 공용 테이블·버킷·큐 데이터 변경. 없으면 "없음" -->

## 워커 재시작
- [ ] 필요 없음
- [ ] 필요 — `services/ocr-worker`·`services/common`·의존성이 바뀌어 머지 후 각자 워커를 재시작해야 합니다 (docs/worker.md)

<!-- 개인정보(실제 영수증·카드번호·이름·전화번호)와 비밀값(비밀번호·토큰·키)을 넣지 않았는지 확인해 주세요 -->
