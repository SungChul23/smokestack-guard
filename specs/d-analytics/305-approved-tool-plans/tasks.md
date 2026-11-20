# 작업 목록: 승인된 도구 조합

입력: spec.md, plan.md, research.md, data-model.md, contracts/approved-plans.md. 로컬 실행 전 검증만 구현한다.

## 준비·공통 기반

- [x] T001 `D/query-router-lab/approved-plans-20261114/`에 원문·기대·초기 실패를 고정하고 변경할 기존 파일을 백업한다.
- [x] T002 `D/dashboard-preview/regional-console/tests/query-router/approved-plans.test.cjs`에 recipe·공유 조건·조작·누락·자료 미보유 실패 검사를 먼저 작성한다.

## US1 — 단일 요청과 능력 경계

- [x] T003 [US1] `D/dashboard-preview/regional-console/query-router/capability-catalogue.js`에 단일 6개·복합 4개·정의/연결 대기·자료 미보유 목록을 구분한다.
- [x] T004 [US1] `D/dashboard-preview/regional-console/query-router/approved-plans.js`에 기존 단일 분석 위임과 kg 총량의 자료 미보유 안내를 구현한다. recipeId와 입력 필드는 허용 목록만 받는다.

## US2 — 복합 계획과 조건 카드

- [x] T005 [US2] `D/dashboard-preview/regional-console/query-router/approved-plans.js`에 ‘복합은 정확히 2단계’, id s1/s2, 등록된 순서·의존성·공유 조건을 강제하고 고정 복합 표현만 해석한다.
- [x] T006 [US2] `D/dashboard-preview/regional-console/query-router/approved-plan-session.js`에 공유 슬롯·단계 슬롯·옵션 ID·TTL=300000ms·문맥 fingerprint·명시 조건 보존·최종 해석 확인을 구현한다.
- [x] T007 [US2] `D/query-router-lab/build-workbench.cjs`와 `manual-review-20261114/review.js`에 새 계획 모듈·단계 표시·복합 조건 카드를 연결하고 기존 단일 UI를 보존한다.

## US3 — 일부 실패 대조

- [x] T008 [US3] `D/dashboard-preview/regional-console/query-router/approved-plans.js`에 테스트 결과 대조기를 구현해 success/no_results/error/blocked_dependency와 partial을 구분한다. 출처 없는 수치/문서 성공, applied 없는 화면 성공을 거절한다.

## 마감

- [x] T009 `D/query-router-lab/check-approved-plans.cjs`, 고정 사례와 기존 전체 단위·`qa-manual-review.cjs`의 실제 Kiwi/브라우저 검증을 실행한다. 실패를 숨기거나 기대값을 바꾸지 않는다.
- [x] T010 `D/query-router-lab/approved-plans-20261114/README_KO.md`에 허용 조합·범위 대조표·흐름도·실행 결과·한계·재현 방법을 기록하고 spec/tasks 상태를 마감한다.

의존: T001→T002→T003/T004→T005→T006→T007, T005→T008, T007/T008→T009→T010. MVP는 US1이다. US2의 계획 작성과 US3의 결과 대조기는 별도 파일 테스트 작성만 병행 가능하지만, 구현은 동일 파일 충돌을 피하도록 순차 수행한다. 실제 DB·모델·LLM·지도 실행은 이 tasks에 포함하지 않는다.
