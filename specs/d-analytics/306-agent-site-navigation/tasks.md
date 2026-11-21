# 작업 목록: 사업장 이동 하나의 실제 실행

입력: spec/plan/research/data-model/contracts/quickstart. 사용자 승인 범위는 단일 사업장 이동이다.

## 준비

- [x] T001 `D/site-navigation/before/`에 변경할 기존 파일을 보관하고 `tests/query-router/site-navigation.test.cjs`의 초기 실패를 남긴다.

## US1 — 명확한 대상 이동

- [x] T002 [US1] `ui-review-20261109/site-navigation-executor.js`에 명령 3필드·명단·좌표·지도 준비 검사와 최대 3초 표시 확인을 구현한다.
- [x] T003 [US1] `console-app.js`에 `selectSiteForAgent`를 추가해 필요한 query/statuses만 완화하고 기존 pick/render/focusSite를 사용한다.
- [x] T004 [US1] `D/site-navigation/build-core.cjs`와 `agent-site-navigation.js`에서 기존 공통 분류·검증 결과를 단일 실행기에 연결하고 성공/일부 적용/오류를 구분한다.

## US2 — 후보 확인과 만료

- [x] T005 [US2] `agent-site-navigation.js/.css`에 명단 후보·취소·원문/명단 fingerprint·TTL=300000ms·새 질문/닫기 이후 무효화를 구현한다.

## US3 — 기존 기능·검증

- [x] T006 [US3] `agent-shell.js`, `agent-exceedance.js`, `hatch-thin.html`에 안내·취소·최소 로드만 연결하고 기존 법령/초과 조회를 유지한다.
- [x] T007 [US3] `D/site-navigation/qa-navigation.cjs`와 전체 단위로 실제 선택·표시·검색/상태 충돌·부분 이름·미등록·취소·오류·기존 검색·모바일/테마를 검사한다. 네이버 실제 SDK 접속은 강제하지 않는다.
- [x] T008 `D/site-navigation/README_KO.md`에 결과·한계·재현·백업과 실제 실행/기존 실험실의 차이를 기록한다.

의존: T001→T002→T003→T004→T005→T006→T007→T008. 단계별 순차 구현. 다른 담당자에게 위임하거나 새로운 서버/데이터 계약을 만들지 않는다.
