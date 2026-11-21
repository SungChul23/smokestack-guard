# 작업 목록: 공통 문서 요청 계약

## 기반

- [x] T001 명세·계획·계약·체크리스트와 변경 전 모듈 보관을 준비한다.
- [x] T002 query-router/request-contract.js와 tests/query-router/request-contract.test.cjs에 원문 결속·역할·출력·typed 슬롯 검사를 먼저 고정하고 구현한다.

## US1·US2 — 요청과 부족 조건 보존

- [x] T003 tool-session.js, document-intent.js, tool-workflow.js에 계약과 typed 부족 슬롯을 연결한다. 구형 조건은 재입력 안내로만 호환한다.
- [x] T004 rag-pipeline.js와 law-evidence-search.js에 같은 요청 계약과 참고/목표 역할을 전달한다.

## US3 — 출력 충족

- [x] T005 answer-contract.js에 전문 manifest·혼합 두 채널·전체 범위 미확인 보류와 계약 결속 검사를 구현한다.

## US4 — 기존 계획 경계

- [x] T006 rag-pipeline.js에 기존305 계획의 dry-run 검증·계약 보존을 연결하고 문서 외 무실행을 검사한다.

## 통합

- [x] T007 build-workbench.cjs를 갱신하고 라우터/문서/계약/브라우저 및 고정48·신규 표현·34,999 회귀를 확인한다.
- [x] T008 CHANGELOG_KO.md에 변경·검증·호환 차이·남은 이슈를 기록하고 실제 완료만 표시한다.

의존성: T001→T002→T003→T004→T005→T006→T007→T008. 출력 검사와 typed 슬롯의 독립 fixtures 작성은 병렬 가능하나 공유 모듈 수정은 순차 수행한다. MVP는 문서 요청 계약·출력 보류이며 실제 운영 실행은 범위 밖이다.

검증 근거: `D/query-router-lab/shared-contract-20261115/CHANGELOG_KO.md`, `release2-summary.json`. 완료 표시는 이 로컬 계약 범위에 한정한다. 신규24문항 독립 의미 검수의 실패4건·추가 검수2건은 미해결로 기록했으며 모든 자연어 통과나 운영 연결 완료를 뜻하지 않는다.

## 후속 흐름 결함 보강 — 2026-11-16

- [x] B001 판정 요청/제외 관계를 분류와 문서 검색에서 공유하고 불필요한 재질문을 검사한다.
- [x] B002 명시된 두 일반 절차 및 단계별 직접 근거를 보존하고 누락 초안을 차단한다.
- [x] B003 잘못된 해석 슬롯은 사용자 조건 부족과 구분해 동일 원문의 형식 재해석1회만 허용한다.
- [x] B004 실제 Kiwi의 별도 신규12·기존24·고정48 문항과 기존34,999 회귀를 재실행하고 독립 검수 기록을 보존한다.
- [x] B005 SC-023·FLOW-008/009의 일반 문서+개별 판정 혼합 요청과 SC-007/017·FLOW-004의 확인 수준·근거 충분성을 해결·재검수한다. 당시 의미 검수36건의 정상30·실패3·추가 검토3은 과거 결과로 보존한다. 후속 D-308에서 해당 사례와 추가 발견 사례를 보강하고 최초104건·보충3건의 독립 검수를 완료했다. 로컬 흐름 범위의 완료이며 운영 API 연결 완료는 아니다.

후속 변경·중간 실패·최종 결과: `D/query-router-lab/flow-first-20261115/CHANGELOG_KO.md`.

최종 보강·재검수: `specs/d-analytics/308-preserved-task-flow/`, `D/query-router-lab/task-flow-20261116/CHANGELOG_KO.md`, `final-summary.json`. 기존 실패·기대값은 변경하지 않았다.
