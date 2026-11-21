# 작업 목록: 연속 질의 PATCH

## 준비
- [x] T001 `query-router/conversation-session.js`의 확정 실행 기록·활성 초점·허용 변경·권한 지문을 설계한다.

## US1
- [x] T002 [US1] 같은 모듈에서 날짜·물질 후속을 기존 분류 앞에 연결하고 절대 기간으로 고정한다.
- [x] T003 [US1] `workbench-20261114/web/app.js`, `build-workbench.cjs`에 세션 연속성을 연결하고 `continuity.html`에서 실제 Kiwi 시연을 제공한다.

## US2
- [x] T004 [US2] 미완료·실패·주제 변경·만료·권한/자료 변경·불명확 변경을 CLARIFY/차단으로 처리하고 신뢰 실행/전달 콜백을 분리한다.

## US3
- [x] T005 [US3] `tests/query-router/conversation-session.test.cjs`에 원본 보존·필드 출처·부모 연결·시연/실제 구분과 반례를 검사한다.

## 마무리
- [x] T006 `D/query-router-lab/continuity-20261116/`에 실제 Kiwi·브라우저·전체 회귀 결과 및 Mermaid를 기록한다.

완료 근거: 전체433개(신규34)·Kiwi125원문·새 브라우저18개·기존 브라우저43개. 실제 측정 실행·외부 LLM 호출·AWS 변경 0. 상세 `D/query-router-lab/continuity-20261116/REPORT_KO.md`.

## 중간 발화·짧은 말투 후속 보강

- [x] T007 [US1] `conversation-language.js`와 `conversation-session.js`에 중립/표현 선호 발화 최대 3턴 유지, 감사 기록, 짧은 날짜·물질 문법을 연결했다.
- [x] T008 [US2] 새 조회·새 법령·실패·만료·권한 변경을 건너뛰지 않으며 ‘네’로 조건을 승인하거나 실행하지 않는지 검사했다.
- [x] T009 [US3] `conversation-bridge.test.cjs`, `bridge-kiwi.cjs`, 작업대 브라우저에서 기록 보존·부모 연결·중간 발화의 출처를 검증하고 Mermaid를 갱신했다.

후속 완료 근거: 전체 Node451개, 중간 발화 관련 새 검사18개, 실제 Kiwi 문맥58개, 새 브라우저25개와 기존 문서·카드43개 통과. 남은 초기 가드 분기2개와 미확정 표현 확인6개를 숨기지 않고 `BRIDGE_REPORT_KO.md`에 기록했다.

의존성: T001→T002→T004→T005→T003→T006. 기본 세션 완료 뒤 별도 시연을 연결한다. 이번에는 순차 작업한다. 실제 조회 API·AWS·운영 프론트 배포는 범위 밖이다.
