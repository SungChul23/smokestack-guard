# 작업 목록: 로컬 TMS 자연어 조회·화면 라우터

## 2026-11-14 영역 분리 실험 후속

- [x] T093 대출/보험 요청에 TMS 관련 여부를 되묻는 문제를 보강했다. 무관한 금융 요청 및 금리/여신 판단을 OUT_OF_SCOPE로 보내고 굴뚝의 법령·대응 비용·관측 근거 요청과 금융 요청 제외 문장은 보존했다. 고정 질문 65개 실제 Kiwi 검사 35→65개 일치, 불필요한 분야 확인 카드 21→0개, 전체 단위 236개·브라우저 18개 통과했다. 이전 480개 중 NP005의 5개 말투는 범위 정책 변경으로 차이를 별도 기록했으며 원 기대·엄격 FAILED 로그를 보존한다. 근거: `D/query-router-lab/unrelated-finance-20261114/README_KO.md`.
- [x] T092 사용자 결정에 따라 사업장 위치 질문을 단순 주소 답변 대신 기존 지도 이동 명령으로 해석하도록 `business-location.js`를 연결했다. 명단상 유일한 정확한 이름/코드는 준비 명령, 동명/부분 이름은 후보 카드, 없는 코드는 명단 내 검색 없음으로 구분한다. 명단 변경 시 세션을 만료시키며 측정/법령 요청을 위치 검색으로 바꾸지 않는다. 실제 관제 실행은 연결하지 않고 성공 안내는 실행 성공 확인 후에만 허용한다. 단위 233개·수동 검수 브라우저 16개 통과, 위치 질문 9개를 별도 검토 묶음으로 제공했다.

- [x] T090 짧은 지역/물질/비율/정렬 생략형과 반례 248개를 보강 전에 고정하고 실제 Kiwi로 전후 검사했다. ‘기준대비+퍼센트’, 문장 끝 ‘높은 거/낮은 거’, 물질 단독 ‘얼마’의 제한된 표현만 정리하고 시각·지표·개수를 추정하지 않는다. 170→248개가 정한 기대 조건을 통과했으며 LLM 후보 86→8개, 준비 완료 10개는 유지했다. 별도 회귀 4개를 추가한 전체 단위 228개와 수동 검수 브라우저 14개를 통과했다. 원문/기대는 변경하지 않고 `D/query-router-lab/short-questions-20261114/`에 증거와 한계를 기록한다.
- [x] T091 기존 검토 기준 18,012개를 재분석해 18,011개 일치와 1개 의도한 동작 변화를 확인했다. TB014161의 기존 LLM 이관이 원문 조건을 보존한 시각 카드로 바뀐 것을 `check-short-regression-delta.cjs`로 대상/물질/비율/초과 부등호/시각 미지정/실제 카드까지 별도 검증했다. 원 고정 기대와 엄격 FAILED 결과는 보존하고 모든 기존 기대 통과로 집계하지 않는다. 이전 480개 정책 검사는 그대로 통과했다.

- [x] T089 사용자 직접 검수용 `D/query-router-lab/manual-review-20261114/`와 `manual_review_server.py`를 분리했다. 기존 사례 묶음·원문 직접 입력·명시적인 화면 문맥 체크·Kiwi/정규화/추출 조건/미해석 표현/분기 결과·조건 카드 재검증·사용자 판정 저장/내보내기를 지원한다. 기대값을 실행 계획으로 주입하지 않는다. 기존 8766/메인 관제/라우터 판단 코드는 유지하고 8767 루프백 별도 화면만 제공한다. 테스트 결과는 해당 폴더 `qa-summary.json`에 남긴다.

- [x] T087 새 페르소나·말투 480개의 최초 입력과 기대를 보존한 채, 등록 이름 보호 후 제한된 인사말·부탁형 어미를 정규화했다. 금지 동작은 대상·동작·가까운 부정·시제를 함께 검사하고, 명시적인 서비스 밖 주제 전환을 구분한다. 부정·제외·복수 조건을 삭제하지 않으며 가동중지 상태 설명과 실제 정지 지시를 구별하는 반례를 추가했다. 전체 단위 224개·브라우저 표본 148개를 통과했다. 최종 전체 회귀와 전후 수치는 `D/query-router-lab/tone-improvement-20261114/REPORT_KO.md`에 별도로 기록한다. 이 480개는 보강에 사용한 개발 회귀 세트이며 독립 사용자 정확도가 아니다.
- [x] T088 보강 후 직접 명령 정확 60→142개, 금지 요청 사전 차단 누락 56→0개, 서비스 밖 분류 누락 35→0개를 같은 480개로 확인했다. 원 기대 차이 10개는 지역 별칭 5개·불명확한 서비스 범위 확인 5개로 별도 검증하며 원 기대를 바꾸지 않았다. 기존 검토 후 기대 18,012개 전부 통과, 기존 전체 입력 43,298개의 정한 의미 불변조건 위반 0개다. 11단계 전체 배치는 코드·입력 변경 없이 `COMPLETED_WITH_KNOWN_LIMITS`로 완료됐다. 사람의 독립 의미 평가와 실제 LLM/DB/화면 실행 완료를 뜻하지 않는다.

- [x] T084 원 기대와 다른 106건을 코드 오류 3건·기대값 수정 48건·의도적 확인/이관 55건으로 문항별 확정했다. `freeze-reviewed-expectations.cjs`는 분기기/실행 결과를 참조하지 않고 원문·원본 파일 해시·검토 근거·고정 기대를 `reviewed-expectations-20261114/expectations.json`에 보존한다. 기존 원문과 기대는 수정하지 않는다.
- [x] T085 부정된 수정 요청의 잘못된 차단과 명확한 표 열기/사업장 지도 이동의 누락을 코드에서 수정했다. 18,012개를 원/검토 후 기대값으로 각각 대조하고, 검사기에 잘못된 대상·위조 시각·없는 카드·다른 이동 대상을 넣으면 실패하는 회귀 검사도 추가했다. `batch-router-audit.py`는 검토 후 실패와 검토 커버리지 불일치로 판정하며 원 기대 통계는 따로 남긴다. 같은 코드 해시의 최신 페르소나 결과만 재사용한다. 최종 수치는 `D/query-router-lab/reviewed-expectations-20261114/REPORT_KO.md`에 기록한다.
- [x] T086 검토 후 기준 18,012/18,012개·브라우저 66/66개·전체 단위 216/216개를 통과했다. 원 기대 차이 103개는 별도 보존하고 검토 후 실패/잘못된 완료/검토 누락/분석 오류는 0이다. 전체 10단계 배치가 코드/기대/원본 변경 없이 `COMPLETED_WITH_KNOWN_LIMITS`로 완료됐다. 실제 LLM/DB/화면 명령 실행은 없다.

- [x] T081 `semantic-policy.js`와 공통 검증기를 보완해 서로 다른 표시 동작·복수 법령 기준일·문서 출력 관계를 축약하지 않도록 했다. TMS 여부가 불명확한 문맥 요청에는 `service_scope` 카드, 모호한 원문/요약 요청에는 `outputFormat` 카드를 제공하며 선택 자체로 명령을 실행하지 않는다. 미연결 동작과 금지 요청을 구분하고 집계의 선택 대상 권한도 재검증한다.
- [x] T082 실제 Kiwi 원문 전체 대조 스크립트 `review-all-corpora.cjs`, 의미 대조 1,169개 `final-review-matrix.cjs`, 후보 자료형·도구 조건 301개 `final-review-validator.cjs`, 진단 재현 `final-review-audits.cjs`와 새 카드 브라우저 검사를 구성했다. 초기 실패/수정 전 모듈과 고정 기대를 보존한다. 최종 실행 수치와 기대값 재검토 사유는 `D/query-router-lab/final-review-20261114/REPORT_KO.md`에 기록하며 미연결 실제 LLM/DB/화면 실행의 완료로 취급하지 않는다.
- [x] T083 기존 43,298개 입력의 의미 보존 검사·새 의미 조합 1,169개·후보 조건 301개·단위 209개·진단 158개·새 카드 브라우저 58개를 확인했다. 기존 말투 1,471개/어순 40개/명령 460개/브라우저 457개/사업장 1,143개/HTTP 19개도 통과했다. 페르소나 원 기대 차이 3개와 구형 기대 차이 103개를 원문별 검토 CSV에 기록했다. 원 기대를 덮어쓰지 않았고 자동 완료 의미 검사 위반·검토 미해결은 0이다. 마지막 과거 연도 범위 확인은 코드 변경 범위와 영향 2개 사례를 별도 증명하고 14,265개 회귀를 다시 확인했다. 실제 LLM/도구 연결 완료를 뜻하지 않는다.

- [x] T080 `semantic-audit-20261114/`의 원문/실제 Kiwi 증거와 수정 전 모듈을 보존했다. 기준값을 실측값으로 소비하는 경로·복수 UI 조건의 마지막 값 채택·기간 순위/단독 물질/정의 질문 모호성을 자동 완료하지 않도록 수정하고 문서 원문/요약을 `outputFormat`으로 보존한다. `semantic-loss.test.cjs`와 수정 후 대조 60개·브라우저 표본 26개로 검증하며 실제 LLM/도구 실행은 없다. 최종 회귀 결과는 `after-fix/REPORT_KO.md`에 기록한다.

- [x] T077 `colloquial-20261114/`에 말투 동치·반례 1,471개를 구현 전에 고정했다. 새 어순 40개도 최초 평가 전에 고정하고 결과에 맞춰 재수정하지 않았다. 기대값은 사람 독립 검수 전 초안이다.
- [x] T078 `request-act-normalizer.js`로 조회·명시 집계·목록·수치 질문·허용 화면 행위를 분리했다. 대상명 보호와 기존 조건 검증을 유지하며 정의·분석·비교를 단순 조회로 바꾸지 않는다.
- [x] T079 같은 말투 세트 기대 일치 295→1,471개, 기존 완료 256개 조건 유지, 브라우저 표본 181개 통과. 새 어순 40개 중 36개 일치·4개 해석 대기이며 단위 179개·기존 명령 460개·브라우저 457개를 통과했다. 기존 페르소나 차이 173개와 이전 기준 차이 121개를 숨기지 않고 `colloquial-20261114/REPORT_KO.md`에 기록했다. 실제 LLM/명령 실행은 없다.

- [x] T074 `free-expression-20261114/before/`에 이전 공통 모듈/검토 기준/브라우저 기준을 보존했다. 별칭·어미·조사·수량·명시 비율 표현을 확장하고 비교·부정·배제·대안은 남겼다.
- [x] T075 `expression-normalizer.js`에서 대상명 보호와 실제 Kiwi 조사 표지 검사를 구현하고 원문을 보존했다. 도메인만 확인되는 질문은 실행 후보가 아닌 해석 후보로 넘긴다. `check-free-expressions.cjs`의 새 원문 46개는 결과 튜닝 없이 기대와 맞았고 자동 인식 0→14개였다.
- [x] T076 같은 페르소나 3,747개 방향 일치 3,490→3,574, 직접 원문 108→136개로 개선됐다. 기존 자동 인식 2,835개 조건 변경/이탈은 0이다. 별도 기준의 40개는 선택시각과 조회시각을 구분해 시간 재확인으로, 복잡 부정 1개는 해석 대기로 바뀌었다. 단위 172개·명령 460개·브라우저 457개/추가31개·사업장1,143개/HTTP19개를 통과했고 잔여 차이와 비용 참고치를 보고서에 공개했다.

- [x] T071 `persona-seeds.cjs`, `generate-persona-questions.cjs`에 12개 하위 역할/직접 작성 원문 192개와 변형·조건 조합을 포함한 고유 질문 3,747개를 고정했다. 각 질문에 참고 답변·의도·누락 조건·현재 지원 범위를 작성했고 실제 측정값·법적 결론은 만들지 않았다. 기대 간 충돌 0개·입력 해시를 보존했다.
- [x] T072 `evaluate-persona-questions.cjs`에서 실제 Kiwi/현재 분기로 3,747개를 한 번 검사했다. 기대 방향 일치 3,490개/재검토 257개, 이 세트의 잘못된 완료 후보 0개·분석 예외 0개다. 해석 이관 294개를 이해 확인 전으로 분리했다. 직접 작성 192개는 방향 일치 108개/재검토 84개다. 라우터 자동 수정은 없다.
- [x] T073 기존 자동 배치 6단계와 브라우저 표본 107개(방향 일치 82/차이 25, 실행 오류 0)를 완료했다. 기존 기준의 추가 회귀는 없고 알려진 87개 차이는 남아 있다. `prepare-persona-review.py`로 전체/직접 원문/불일치 CSV·사람 검토 칸과 이동 가능한 ZIP을 만들었다. 결과는 `persona-questions-20261114/REPORT_KO.md`와 배치 최종 상태에 공개했다.

- [x] T070 사용자의 토큰 절약 지시에 따라 `D/query-router-lab/batch-router-audit.py`에 고정 기대 기반의 한 차례 자동 일괄 실행·원문/불일치 보존·버전 해시·결과 보고를 구성하고 백그라운드 실행했다. GPT/LLM·자동 코드 수정·시간 채우기 반복은 없다. 최종 상태/남은 차이는 `batch-audit-20261114/latest.json`과 보고서에서 확인한다.

- [x] T066 `validate-command-flow.cjs`에 고유 원문 458개/문맥 포함 460개와 도구·대상·물질·시간·부등호·지표·집계 기대를 고정했다. 카드 대화 9개를 포함했다.
- [x] T067 실제 Kiwi/세션의 최초 실패 6개(잘못된 READY 5개)를 `flow-validation-20261114/*-initial.json`에 보존했다. 수정 후 460개 기대 검사를 통과했고 원문 이해와 요청 재작성을 구분했다.
- [x] T068 상충 개수/방향/지표/경계/집계 정의의 마지막 값 덮어쓰기를 막고 다중 물질 카드에서 대상·기간·작업을 보존했다. 범위 축소 뒤 최종 확인을 요구한다. 단위 164개 통과, 기존 14,265개 재검사의 불일치 87개는 그대로 남았다.
- [x] T069 `qa-command-flow.cjs`에서 457개 원문/8개 카드 흐름을 실제 브라우저로 확인했다. 이전 근거 fixture 3개는 엔진에서만 검사했다. `build-flow-report.cjs`로 CSV·보고서·흐름도·해시를 작성했다. 실제 LLM/명령 실행은 없다.

- [x] T061 `D/query-router-lab/workbench_server.py`에 루프백 Kiwi API·공개 명단/후보 검색을 구현했다. 요청 크기·Origin/Host·정적 경로·오류 등 HTTP 검사 19개 통과. 기존 수정 대상 백업/기존 검토 화면의 기준 모듈을 보존했다.
- [x] T062 `tool-session.startExplicit`과 명단/지역/별칭 버전 검사를 추가했다. `workbench.test.cjs`를 포함한 기존 분기·카드·문맥 회귀 160개 통과. 특정 사업장 ID는 요청에 기록하고 명시적 현재사업장 지칭과 주변 선택을 구분했다.
- [x] T063 `D/query-router-lab/workbench-20261114/web/`에 고정 질문 8종·실제 Kiwi 자유 입력·지역/사업장/굴뚝 선택·단계별 카드·무실행 요약을 연결했다. 실제 LLM/조회/화면 명령은 연결하지 않았다.
- [x] T064 기존 `agent-exceedance.js`에 별도 로컬 실험실 링크만 추가하고 기존 관제 진입과 법령/초과 조회 진입 보존을 브라우저에서 확인했다.
- [x] T065 실제 HTTP/Kiwi 개발 질문 1,143개·HTTP 19개·브라우저 26개 통과. 기존 14,265개 기준은 저장된 실제 Kiwi 토큰으로 재검사해 기존 불일치 87개가 그대로 남음을 공개했다. `workbench-20261114/REPORT_KO.md`에 초기 실패·수정·잔여 한계를 기록했다.

- [x] T058 Kiwi·Microsoft Entity components·Rasa 공식 문서에서 명단 검색/의도/조건 수집의 분리 방식을 조사하고 `D/query-router-lab/separation-20261114/REPORT_KO.md`에 적용 제안과 미도입 범위를 기록했다.
- [x] T059 `D/query-router-lab/separation_experiment.py`로 실제 909개 명단의 이름 조각 5,286개와 Kiwi 기본/사전 추가 909개를 비교했다. 후보 검색과 토큰 경계를 의미 이해 정확도로 표현하지 않고 모든 후보·실패를 보존했다.
- [x] T060 고정 질문 제안 8종의 등록 변형 16개/비등록 25개를 구분하고 `check-separation.cjs`의 기존 검증기 연계 검사 57개를 통과했다. 실제 LLM·명령 실행·메인 화면 연결은 없다.

입력: [spec.md](spec.md), [plan.md](plan.md), [data-model.md](data-model.md), [내부 계약](contracts/local-query.md).  
상태: **일반 질의 기능 T001~036은 미완료다.** 작성일 2026-11-13. 테스트는 원본 설계의 선행 테스트 요구에 따라 포함한다. 화면 물질 잠금과 후속 US6의 실행 전 분기 검증 T037~041만 적용했으며, 일반 기능 전체를 완료한 것으로 체크하지 않는다.

각 작업의 경로는 저장소 루트 기준이다. `[P]`는 파일과 선행 조건이 독립일 때 병행 가능하다는 표기이며, 자동 에이전트 실행 지시가 아니다. 테스트 표본은 시험용으로만 사용하고 운영 화면에 가상 측정값을 넣지 않는다.

## 단계 1 — 준비

- [ ] T001 `D/query-router-planning/before-implementation/`에 변경 대상 파일만 백업하고 `D/query-router-planning/baseline-hashes.json`에 기존 원문·좌표·자료 인덱스 해시와 실행 환경을 기록한다. 수집기·원본 자료·Git 브랜치는 변경하지 않는다.
- [ ] T002 `D/dashboard-preview/regional-console/tests/query-router/fixtures/normal.json`, `adversarial.json`, `catalogue-map.json`에 원본 A~K 질문을 누락 없이 추출하고 각 ID의 로컬 기대 경로·추출 조건·금지 실행을 기록한다. 사용자 11개 결정의 잠금/지원 범위 override를 표시하며 모두 차단으로 통과시키지 않는다.
- [ ] T003 `D/dashboard-preview/regional-console/query-router/README_KO.md`에 303 범위·예정 테스트 명령·기존 함수 의존성을 기록하고 `.github/CODEOWNERS`의 새 코드 폴더 리뷰어를 확인한다. D 기반/자료가 ignore 상태인 사실과 공유 재현 미검증을 명시한다.

## 단계 2 — 공통 기반

모든 사용자 스토리는 이 단계 이후에 진행한다. 결과를 만들기 전에 조건을 검증할 수 있어야 한다.

- [ ] T004 `D/dashboard-preview/regional-console/tests/query-router/schema.test.cjs`에 `question: 정규화 후 1~1000자`, `intent: latest/list/rank/aggregate/status/view/legal/unknown`, `kind: answer/clarification/unsupported/blocked/error`, `limit: 양의 정수 N`, `UNKNOWN 실행 금지`의 실패 사례부터 작성한다.
- [ ] T005 `D/dashboard-preview/regional-console/query-router/schema.js`, `capabilities.js`에 내부 구조 검증과 `NOx·SOx만 해금`, `TSP·HCl·CO·NH3·HF는 POLLUTANT_LOCKED`, 조건 출처 `question/ui/confirmed`, 미확정·잔여 조건 무실행을 구현한다. 화면에 먼저 추가한 `D/dashboard-preview/regional-console/pollutant-capabilities.js`의 지원 설정을 재사용하고 물질 목록을 중복 정의하지 않는다. LLM/SQL/쓰기/외부 연락/설비 도구는 등록하지 않는다.
- [ ] T006 `D/dashboard-preview/regional-console/query-router/time.js`, `context.js`에 실제 received_at·선택 selectedSite/stack·보관 기준시각·자료/정책/capability 버전 fingerprint를 분리한다. `달력 [from,to)`, `최근/화면 from<=t<=to`, 종료가 시작보다 뒤라는 제약과 질문 명시 조건 우선·다중 선택 확인을 구현한다.
- [ ] T007 [P] `D/dashboard-preview/regional-console/tests/query-router/status-policy.test.cjs`에 단계·경계·버전 변경, 100%의 수치 부등호, 사용자 경고선 독립, 잠금 HCl이 대표 상태를 만든 사례, 잘못된 경계 순서 거부를 먼저 작성한다.
- [ ] T008 `D/dashboard-preview/regional-console/display-status-policy.js`에 버전·temporary·순서 있는 단계/경계/연산/색상 토큰/정상·미판정·우선 확인 구간을 정의하고 검증한다. 현재 기본 단계의 의미를 보존하며 정책 변경으로 원 응답 기준값을 바꾸지 않는다.
- [ ] T009 `D/dashboard-preview/regional-console/data-model.js`, `ui-review-20261109/console-app.js`, `map-engine-interactive.js`, `map-engine-naver.js`, `hatch-thin.html`의 상태 소비자를 T008 공통 설정으로 연결한다. `urgent>=90`, allStatuses·라벨·색상·하단 범례 등 분산 상수를 대조하고 수치 `>100/≥100`·사용자 경고선은 독립 유지한다.
- [ ] T010 `D/dashboard-preview/regional-console/query-router/validator.js`, `router.js`에 엔터티 소속·물질 잠금·범위·지표·시점 정렬·단위/기준 출처·부정 전체·조회 한계·로컬 capability·문맥 버전 검사를 구현한다. 운영 인증 완료로 표현하지 않으며 미연결 실행기는 unsupported로 반환한다.

## 단계 3 — US1: 선택 굴뚝 최신 보관값 (P1)

독립 인수: 선택/명시한 굴뚝의 최신 원문·시각을 읽고 잠금 물질은 실행하지 않는다.

- [ ] T011 [US1] `D/dashboard-preview/regional-console/tests/query-router/archive-reader.test.cjs`, `execution.test.cjs`에 최신 상태문자/NULL의 과거 숫자 대체 금지, 선택 A/질문 B, 중복 이름·굴뚝 소속 오류, 잠금 5종 무실행, 질문 HTML 비실행을 작성한다.
- [ ] T012 [US1] `D/dashboard-preview/regional-console/query-router/archive-reader.js`에 `snapshotLatest()`를 구현한다. 원본 최신 자료의 불변 읽기 관점을 유지하고 화면 observations 교체에 영향받지 않으며 원문·unit_source·source_ref·자료 revision을 보존한다.
- [ ] T013 [US1] `D/dashboard-preview/regional-console/query-router/parser.js`에 지원하는 최신값·원문 상태·현재/지금 질의의 전체 문법과 확정 별칭만 구현한다. NOx/SOx를 로컬 코드로 매핑하되 SO₂를 SOx와 임의 동일시하지 않고 잔여 조건/부정이 있으면 미확정으로 남긴다.
- [ ] T014 [US1] `D/dashboard-preview/regional-console/query-router/read-executor.js`에 latest_measurements/display_status를 구현한다. 각 굴뚝 실제 최신 측정시각·비실시간·단위/기준 출처·대표 상태 적용 물질 범위를 표시하고 잠금 물질 원인을 NOx/SOx 원인으로 바꾸지 않는다.
- [ ] T015 [US1] `D/dashboard-preview/regional-console/query-router/controller.js`, `result-view.js`, `ui-review-20261109/agent-shell.js`, `hatch-thin.html`에 요청 고정·응답 종류별 템플릿·취소·로딩/오류 안내를 연결한다. 읽기 질문은 지도/그래프를 이동시키지 않으며 문자열을 textContent로 렌더링한다.

## 단계 4 — US2: 확인 질문과 안전한 해석 (P1)

독립 인수: 범위·지표 등 미확정 조건을 확인하는 동안 자료/화면 실행은 0회다.

- [ ] T016 [US2] `D/dashboard-preview/regional-console/tests/query-router/interpretation.test.cjs`에 F~K 전 카탈로그의 기대 경로·조건·금지 실행, 범위+지표 동시 미정, 복합/이중 부정, 명확한 정정과 실제 지원 질문의 구분을 검증한다.
- [ ] T017 [US2] `D/dashboard-preview/regional-console/query-router/parser.js`, `validator.js`에 대상·물질·범위·N·지표 생략 및 부정/비교 범위의 확인 이유를 추가한다. 숫자·키워드 일부만 매칭해서 실행하지 않고 불명확한 복합 요청은 전체를 확인/미지원 처리한다.
- [ ] T018 [US2] `D/dashboard-preview/regional-console/query-router/context.js`, `controller.js`에 메모리 확인 세션과 허용 optionId·보존 IR을 구현한다. 새 질문/취소/창 닫기/자료·설정·선택 변경 시 만료하며 오래된 확인 결과를 새 화면 대상으로 바꾸지 않는다.
- [ ] T019 [US2] `D/dashboard-preview/regional-console/query-router/result-view.js`, `ui-review-20261109/agent-shell.js`에 범위·지표 확인 버튼과 보존 조건 요약을 연결한다. 옵션 클릭 후에도 검증기를 다시 통과시키고 정상 성공과 단순 차단을 구분해 보고한다.

## 단계 5 — US3: 명확한 화면 명령 (P2)

독립 인수: 명확한 허용 명령은 즉시 반영하고, 애매하거나 오래된 명령은 반영하지 않는다.

- [ ] T020 [US3] `D/dashboard-preview/regional-console/tests/query-router/execution.test.cjs`에 허용 명령·임의 함수/URL 금지·잠금 물질 표시 금지·늦은 A 요청 중 B 선택·창 닫기의 무부작용 사례를 먼저 작성한다.
- [ ] T021 [US3] `D/dashboard-preview/regional-console/query-router/parser.js`에 사업장/지역 이동·조회 기간·NOx/SOx 표시·측정값 표 열기 명령을 식별하고 대상·동작을 완전히 검증할 수 있을 때만 view 계획을 만든다.
- [ ] T022 [US3] `D/dashboard-preview/regional-console/query-router/view-executor.js`에 계약의 select_business/select_region/set_chart_range/set_period/set_pollutant_visibility/show_measurement_table만 연결한다. 기존 지도 컨트롤러를 재사용하고 반영 직전에 문맥/소속/버전을 재검증한다.
- [ ] T023 [US3] `D/dashboard-preview/regional-console/query-router/controller.js`, `result-view.js`에 실제 적용한 대상·기간 안내와 stale 응답 무효화를 연결한다. 사용자가 명시하지 않은 지도 배경·개인 설정·다운로드 변경은 추가하지 않는다.

## 단계 6 — US4: 참고 계산·최신 목록/순위 (P2)

독립 인수: 0/10/20/상태/NULL은 평균 10·최대 20·계산3/제외2이며, 전체 최신 순위는 사업장 방문 순서와 독립이다.

- [ ] T024 [US4] `D/dashboard-preview/regional-console/tests/query-router/archive-reader.test.cjs`, `execution.test.cjs`에 숫자 0/쉼표/음수·문자/NULL·기준0·단위 미확인·달력/보관 시간·정확히100%·부분 기간·파일 실패·시점 불일치 비교·방문 순서 독립성을 먼저 작성한다.
- [ ] T025 [US4] `D/dashboard-preview/regional-console/query-router/archive-reader.js`, `ui-review-20261109/console-archive-history.js`에 인덱스/파일 캐시와 원문 expand를 재사용하는 `readHistory(siteId, range, revision, cancellation)`를 구현한다. 화면 선택·활성 observations를 변경하지 않고 사업장·revision·same-origin 경로를 검증한다.
- [ ] T026 [US4] `D/dashboard-preview/regional-console/query-router/parser.js`, `time.js`, `validator.js`에 단일 굴뚝 평균/최대·최신 수치 조건 목록·순위와 실제 KST 어제/보관 기준 최근N시간·`초과 gt/이상 gte`를 연결한다. 미확정 지표/범위/N/정렬 시점은 확인하며 전체 과거 집계/순위는 미지원으로 남긴다.
- [ ] T027 [US4] `D/dashboard-preview/regional-console/query-router/read-executor.js`에 숫자 관측 산술 평균·최대·0 포함·상태/NULL 제외·각 건수, 최신 목록/순위를 구현한다. 일반 순위에 `records.all()`의 일부 이력이나 `localRanking`의 초과 빈도를 사용하지 않는다. 0건/자료 없음/읽기 실패를 구별한다.
- [ ] T028 [US4] `D/dashboard-preview/regional-console/query-router/result-view.js`에 requested_range·observed_first/last·포함/제외 이유·실제 측정시각·지표 정의·자료/정책 버전·단위/기준 제한을 표시한다. 팀 기대 슬롯 계약 없이 공식 결측률·학습 유효값으로 표현하지 않는다.

## 단계 7 — US5: 기존 법령 근거 경로 (P2)

독립 인수: 302 검색의 원문/출처/기준일 제한을 유지하고 예측·원인·제어를 만들지 않는다.

- [ ] T029 [US5] `D/dashboard-preview/regional-console/tests/query-router/execution.test.cjs`에 확보 기준일/다음 날 오늘 법령·원문 링크 검증·근거 없음·잠금 물질 세부 요청·모델 미연결/원인 단정/설비 제어 무실행 사례를 작성한다.
- [ ] T030 [US5] `D/dashboard-preview/regional-console/query-router/law-adapter.js`에 `TmsLawSearch.validate/search()` 재사용과 실제 KST 날짜의 asOf 전달을 구현한다. 기본 확보일로 오늘 질문을 대체하지 않고 302의 status/evidence/as_of/limitations를 보존한다.
- [ ] T031 [US5] `D/dashboard-preview/regional-console/query-router/router.js`, `result-view.js`, `ui-review-20261109/agent-shell.js`에 근거 카드·문서 기준일·검색 실패 재시도를 재사용한다. LLM/모델 호출을 추가하지 않고 요청 종류별 미연결 이유를 표시한다.

## 단계 8 — 교차 검증과 인수

- [ ] T032 `D/dashboard-preview/qa-query-router-20261113.cjs`에 5개 스토리의 실제 파일·질문·확인·통계·늦은 응답·다크/라이트·모바일·키보드·양 지도 화면 명령을 연결한 브라우저 검사를 작성하고 실행한다. 네이버 실연결 검사를 하지 않았으면 별도 미검증으로 적는다.
- [ ] T033 `D/dashboard-preview/regional-console/tests/query-router/fixtures/catalogue-map.json`과 전체 `*.test.cjs`를 대조해 원본 A~K ID 누락·중복·추출 조건·금지 실행을 검증한다. 구현된 정상 질문과 기대 확인/잠금/차단/미지원의 실측 결과를 분리한다.
- [ ] T034 `D/query-router-planning/validation-results.json`에 테스트 실행/통과/실패/미검증·모델/수집 API 호출0·원본/좌표 해시 보존·질문 영속 저장 없음·현재 메모리/파일 로딩 범위를 기록한다. 문서만 작성한 작업을 구현 완료로 체크하지 않는다.
- [ ] T035 `D/dashboard-preview/qa-chart-focus-20261112.cjs`, `qa-law-evidence-20261112.cjs`, `qa-map-inline-20261112.cjs`, `qa-naver-drag-20261112.cjs`와 기존 차트 축 단위 테스트로 기존 기능 회귀를 확인한다. 새 구조에 따라 정당한 검사 경로만 갱신하고 의미 검증을 삭제해 통과시키지 않는다.
- [ ] T036 `D/dashboard-preview/regional-console/query-router/README_KO.md`, `specs/d-analytics/303-local-query-router/quickstart.md`에 실제 구현 범위·실행 결과·미지원·팀 인계 항목·공유 재현 제한·복구 경로를 반영하고 스토리별 인수 후에만 해당 작업을 완료 표시한다.

## 의존 순서와 작은 전달 단위

`준비(T001~003) → 공통 기반(T004~010) → US1(T011~015) → US2(T016~019)`가 첫 MVP다. **첫 사용 결과는 선택한 NOx/SOx 보관값과 시각을 답하고, 모호하면 확인하며, 잠금 물질은 실행하지 않는 질문창**이다.

그 뒤 `US3(T020~023) → US4(T024~028) → US5(T029~031) → 교차 인수(T032~036)` 순서로 작게 확인한다. 명세상 독립 인수는 가능하지만 같은 parser/controller/result-view를 고치는 구현 작업을 동시에 편집하지 않는다.

## 병행 가능한 예시

- 기반: T007의 독립 정책 테스트 초안은 T005/T006과 파일 충돌 없이 진행할 수 있다. T008/T009는 T007과 기반 규약 이후에 한다.
- US1: T011의 스냅샷·중복 대상 표본 검토와 T013의 문법 설계 검토는 가능하지만 실제 구현은 실패 테스트를 확인한 뒤 진행한다.
- US2: 반례의 예상 경로 검토와 확인 버튼 문구 검토는 가능하다. T017~019의 공통 파일 변경은 순차 진행한다.
- US3: 두 지도에서의 동작 인수 시나리오 검토는 실행기 구현과 별도로 준비할 수 있다. 실제 브라우저 검증은 연결 후 수행한다.
- US4: 통계 손계산 표본과 읽기 파일 범위 표본 검토는 독립이다. 실제 계산기/파서 통합은 T025/T026 이후다.
- US5: 기존 302 결과 표본 검토와 오늘 날짜 제한 검토는 독립이다. 새 corpus/법령을 임의 수집하는 작업은 포함하지 않는다.

## 요구사항 추적

| 요구 | 작업 |
|---|---|
| FR-001 | T006, T010, T011, T013, T018 |
| FR-002 | T005, T011, T020, T029 |
| FR-003 | T012, T014, T024 |
| FR-004 | T006, T024, T026, T030 |
| FR-005 | T016~019, T026 |
| FR-006 | T024, T025, T027, T028 |
| FR-007 | T010, T014, T024, T028 |
| FR-008 | T007, T024, T026 |
| FR-009 | T007~009, T014 |
| FR-010 | T020~023 |
| FR-011 | T012, T024~028 |
| FR-012 | T002, T005, T010, T016~019 |
| FR-013 | T005, T010, T020, T029, T034 |
| FR-014 | T029~031 |
| FR-015 | T006, T012, T014, T028, T031 |
| FR-016 | T018, T020, T023, T032 |
| FR-017 | T003, T010, T028, T036 |
| FR-018 | T009, T032, T035 |

## 팀 대기 사항 — 실행 작업으로 만들지 않는 항목

C의 Silver/고유 ID/유효값/상태/단위, E의 확정 판정/예측 출력/모델 지원 범위, A의 질의 서버/운영 인증/배포, 법령 최신성·시설 적용성·승인 SOP는 자료 수령 후 별도 기능으로 계획한다. 이번 36개 작업에 임의 스키마·가짜 예측·실제 알림·새 클라우드 서비스를 끼워 넣지 않는다.

## 후속 범위 — US6 실행하지 않는 Kiwi 분기 검증

사용자의 대량 질문/실제 kiwipiepy/LLM 분기만 검사 요청에 해당한다. 아래 완료는 위 T001~036 전체 기능의 완료가 아니다. schema/parser/time/validator/router는 이 실험을 위한 좁은 Node 프로토타입이며 웹 연결·자료 실행은 없다.

- [x] T037 [US6] `D/query-router-lab/.venv/`, `requirements-lock.txt`, `kiwi_worker.py`에 실제 kiwipiepy 0.24.1 / CoNg 로컬 분석 환경과 JSONL 토큰·부정/비교 표지 출력을 마련하고 버전을 고정했다.
- [x] T038 [US6] `D/dashboard-preview/regional-console/query-router/schema.js`, `parser.js`, `time.js`, `validator.js`, `router.js`, `capabilities.js`에 전체 문법 기반 실행 전 분기를 구현하고 공유 지원 물질 설정을 재사용했다. LLM 후보·법적 검토·확인·미지원·차단은 별개이며 모두 무실행이다.
- [x] T039 [US6] `D/query-router-lab/generate-cases.cjs`, `D/dashboard-preview/regional-console/tests/query-router/fixtures/`에 원본 182개·기준 80개·지원 문법·부정/조건 변형·잠금·미사용 자연어·무작위/경계의 기대값/불변조건을 구분해 21,963건을 생성했다. 기대값은 독립 사람 검수 완료가 아닌 AI 작성 초안임을 명시했다.
- [x] T040 [US6] `D/query-router-lab/evaluate.cjs`, `D/dashboard-preview/regional-console/tests/query-router/routing.test.cjs`에서 실제 Kiwi 결과를 연결해 21,963건과 회귀 84개를 실행했다. 1차 오류를 보완하고 카탈로그/미사용 자연어의 남은 92건 불일치를 보고서에 남겼다. 모양만 정상인 LLM 후보에 실행 권한을 주지 않는다.
- [x] T041 [US6] `D/query-router-lab/make-report.cjs`, `results/REPORT_KO.md`, `review.html`, `all-questions.csv`, `routing-flow.mmd`에 전체 요청·분기·형태소·오류·흐름도·재현 방법을 제공했다. 결과 검토 페이지의 필터/검색·문자열 비실행과 전달 ZIP을 검사한다.

요구 추적 추가: FR-019 → T037/T039~041, FR-020 → T038/T040/T041, SC-009 → T039~041. Kiwi 환경·범위의 후속 변경으로 기존 첫 기능 작업들을 자동 완료 체크하지 않는다.

## 후속 범위 — 상황별 조건 카드 분기

### 후속 승인 — 92개 불일치의 분기·실행 조건 검토

### 후속 승인 — 허용 도구 우선 대량 질문·후보 검증

- [x] T054 `query-router/tool-catalogue.js`에 분석 허용 6개/연결 대기 2개를 명시하고 `tool-workflow.js`, `tool-session.js`에 전체 문법·실제 Kiwi 의미 표지·공통 조건 검증·카드·LLM 모양 후보 재검증/최종 확인을 실행 없이 구성했다.
- [x] T055 `D/query-router-lab/tool-generate.cjs`에서 14,265개 사례를 생성해 실제 kiwipiepy 0.24.1/CoNg로 분석했다. 분석 예외 0건. 생성 문법/조건 누락·문맥·금지·별도 자연어 30개·기존 참고 92개를 구분했다.
- [x] T056 `tool-evaluate.cjs`에서 도구·분기·조건·무실행을 확인했다. LLM 모양 제안 216개에서 632개 조건/확인 검사를 통과했다. 별도 자연어 21개와 기존 참고 66개의 불일치 총 87개는 그대로 공개했으며 실제 LLM/DB/화면 명령 실행은 없다.
- [x] T057 `tool-benchmark-20261113/`에 계약/전체 CSV/실패/요약/흐름도와 표본 285개(실패 87개 전부 포함)의 카드 검토 화면을 제공했다. 단위 150개·브라우저 14개 통과. RDS/실제 LLM/일반 웹 에이전트의 전체 연결은 대기다.

- [x] T050 기존 92건과 요약을 `D/query-router-lab/triage-20261113/`에 해시와 함께 보존했다. 질문별 재분류 근거·확정/부족 조건·의미 모호성·실행 조건을 사람 검수 전 초안으로 작성했다. 사용자 문맥 정책 변경 전 초안도 별도로 보존했다.
- [x] T051 기존 실제 Kiwi 분석을 원문과 대조해 재사용하고 현재 라우터·카드 첫 응답 및 21,963건 회귀를 실행 없이 재검사했다. 원래 불일치 92건은 그대로다. 추가 규칙 개발 사례 20개 중 6건의 원시 분기 차이를 공개했고 LLM/도구 실행은 없다.
- [x] T052 92건 전체 JSON/CSV/MD와 검색·필터 가능한 검토 화면 및 흐름도를 제공했다. 질문 문맥·법령/모델 근거·카드 변경 확인·공통 실행 검증의 후속 작업을 구현 완료와 구분했다.
- [x] T053 사용자가 확인한 엄격한 조건/이전 답변 문맥을 `query-router/context-policy.js`에 실행 없는 검증기로 구현했다. 카드 mapTime 검사는 의존 요청으로 제한하고 17개 문맥 검사·22개 카드·85개 기존 분기 검사를 통과했다. 자연어/웹 실행기의 전체 연결은 대기다.

### 후속 승인 — 초과 이력 질문 조회 (FR-022)

- [x] T046 고정 Top 5 및 자동 전체 순위 읽기를 진입점에서 제거하고 `ui-review-20261109/before-exceedance-query-20261113/`에 백업을 보존했다.
- [x] T047 `ui-review-20261109/exceedance-query.js`에 순수 조건 검증·30분 수치 횟수·연속 관측 구간·경계/결측/중복 처리를 구현하고 `tests/query-router/exceedance.test.cjs`의 손계산 표본 7개를 검증했다.
- [x] T048 `ui-review-20261109/agent-exceedance.js`에 기존 질문창 원문·기간·범위·사업장·NOx/SOx·집계 방식 확인 폼과 로컬 읽기 실행기를 연결했다. 기존 법령 검색은 유지하며 전체 범용 라우터·Kiwi·LLM의 웹 연결은 아니다.
- [x] T049 `D/query-router-lab/qa-exceedance.cjs`에서 실제 로컬 자료 조회·취소/늦은 응답·재조회 캐시·빈 결과·375/390px 및 두 테마·기존 법령/지도/선택 차트를 포함한 20개 검사를 확인했다. 기존 분기/카드 포함 단위 검사는 112개 통과했다. `results/EXCEEDANCE_REPORT_KO.md`에 범위와 한계를 기록했다.

사용자가 해석이 어려운 요청을 카드로 구체화하도록 추가 요청했다. 실행 전 검증기와 별도 시안에 적용하며 실제 관제 질문창·데이터 실행기·LLM을 연결한 것으로 취급하지 않는다.

- [x] T042 [US2] `D/dashboard-preview/regional-console/query-router/clarification.js`에 원 분기별 부족 조건·요청 재작성·잠금/모델/원인/법적 검토 대안·차단 안내를 구현했다. 확정 조건 보존과 선택 후 동일 검증기 재검증, 옵션 ID 제한, 화면 fingerprint·TTL·새 질문/취소에 따른 만료를 적용했다.
- [x] T043 [US2] `D/dashboard-preview/regional-console/tests/query-router/clarification.test.cjs`, `D/query-router-lab/evaluate-cards.cjs`로 카드 20개·기존 분기 85개 단위/회귀와 1,440개 조합 흐름을 검증했다. 현재사업장 접두어 소실과 영어 단어 앞 CO 잠금 누락도 수정했다. 원래의 21,963건 자연어 분기 결과를 카드 완료율로 덮어쓰지 않는다.
- [x] T044 [US2] `D/query-router-lab/build-cards-demo.cjs`, `D/dashboard-preview/regional-console/ui-review-20261109/query-cards-preview.html`에 실제 측정값 없는 분기 검토 시안을 만들고 `D/query-router-lab/qa-cards.cjs`의 브라우저 검사 14개로 선택/키보드 초점·문맥 변경·입력 문자열 비실행·모바일을 확인했다.
- [x] T045 [US2] `D/query-router-lab/results/CARDS_REPORT_KO.md`, `cards-flow.mmd`, `README_KO.md`에 조건부 안내·확정 요청·재현 방법·무실행 경계를 기록했다. FR-021/SC-010에 해당하며 전체 운영 질의 실행 완료는 아니다.

### 후속 승인 — 최초 질문부터 실제 문서 읽기·Luna 교차 검수 (2026-11-14~15)

아래 완료는 실험실의 좁은 읽기 경로이며 원래 T001~036 또는 메인 관제 전체 연결의 완료가 아니다.

- [x] T058 `rag-pipeline.js`로 실제 Kiwi/기존 세션/조건 및 해석 확인 뒤 `search_documents`만 로컬 공식 문서 검색에 연결했다. 최초 질문 전체·기준일 전달, 원문 일치·권한/버전·만료·취소·후속 조건 묶음을 검사했다.
- [x] T059 기존/신규 질문 34,999개를 실제 Kiwi로 재분석하고 초기 분류를 보존했다. 상세 연결 473개와 실제 Luna 해석 214개를 별도 기록했다. 자동 확인 입력은 시험 사용자 응답으로 표시한다.
- [x] T060 8768 실험실 자유 입력 경로에 검색 원문·출처와 추가 조건 폼을 연결했다. 회귀 266개, 연결 검사 13개, 실험실 브라우저 31개와 연결 브라우저 10개를 확인했다. 메인 8765와 고정 카드 계획 경로는 별도다.
- [x] T061 실제 검색 결과/비실행 사유로 Luna 답변 초안 473개를 만들고 인용 범위·원문 인용·최초 질문 ID를 검사했다. 구조 오류 8개를 고쳐 숨기지 않고 원본으로 보존했다.
- [x] T062 작성자와 다른 Luna의 473건 전건 의미 검수를 모아 최초 질문/실제 검색/Luna 답변/검수 이유 CSV와 보고서를 완성했다. AI 의견은 처리 적절 393·오류 40·추가 검토 40이며 정답률이 아니다. 인용 검사와 합쳐 86개 생성문을 파생 전달 결과에서 보류했다. 누락/중복/상충은 0건이며 문맥 추정에 대한 검수 이견·초기 실패를 보존했다. 오류 원인의 수정 완료를 의미하지 않는다.
- [ ] T063 메인 질문창의 공통 실행기 통합, 실시간 모델 API, 데이터/화면/예측 도구 연결은 별도 명세·확정 입력을 받은 후 진행한다. 이번 검증으로 완료 처리하지 않는다.

### 후속 승인 — 상태·적용 범위와 부분 답변 후속 검증

- [x] T069 기존 검토 대기 6개 분기·보류 4개 답변을 진단하고 준비/검색/답변 검증 상태를 분리했다. 인사자료 범위 밖, 양식·예시 미확보, 신고 유형 확인을 명시했다. 기존 `decision.route`는 유지했다.
- [x] T070 적용 범위 태그·부분 안내·사용자 확인 보고 종류를 답변 계약에 반영했다. 이전 통과 8개와 보류 4개를 수정해 12개 검수(직접 적절 7, 별도 내용/범위 평가 5)를 기록했다. 후자 5개는 범위 내 설명 완료 1·부분 안내 4로 나누었으며 기존 검수 의견을 덮어쓰지 않았다.
- [x] T071 기존553+신규24의 577건을 실제 Kiwi 기반으로 재실행했다. 새 답변 4개와 기존 검토 대상 10개의 흐름은 독립 검수를 받았다. 신규24의 적절18·오류의견4·추가검토2를 그대로 보존하고 오류 의견은 파생 결과에서 보류했다. 전체 577건을 새 의미 검수한 것은 아니다.
- [x] T072 전체34,999 회귀의 문서 외 준비 명령4,055건 보존, 라우터266·상태/조건17·기존 답변계약31·법령216(정책 차이1 원본 보존)·기존 연결13·브라우저31/17을 확인했다. `rag-refinement-20261115/REPORT_KO.md`, CSV, 485개 원문 인용 무결성 검사를 남겼다. 실시간 앱 LLM/API·RDS·메인 공통 실행기 통합 완료는 아니다.

### 후속 승인 — 요청 경계와 사용자 조건 전달 보강 (2026-11-15)

- [x] T073 기존 문제 6건과 코드 수정 전 생성한 신규 24건을 분리·보존했다. 본문·참조 별표 미검증, 인사자료 범위 밖, 현장 진단·부품 결정 및 개별 법적 판정의 기능 제한과 근거 위장 거절을 명시했다. 명시한 다른 법령을 같은 번호의 보관 조문으로 대체하지 않는다.
- [x] T074 Luna의 부족 조건을 허용된 조건 종류의 고정 라벨로 바꾸어 재입력 카드에 전달했다. 보충 정보를 원래 질문과 함께 실제 Kiwi로 다시 분석하며 일반 필드 입력으로 검증을 우회하지 않는다. 복합 조회·문서 요청과 지원 불가·거절 안내를 화면에 보존했다. 사용자가 말한 자료 보유 상태는 도구 검증과 구분한다.
- [x] T075 기존577+신규24의 601건을 재실행하고 검색 인용2,440개의 원문 일치를 확인했다. 최초 배치의 시계 만료와 ISO 날짜 기본값 보충 오류를 보존·수정했다. 배치만 고정 시계를 사용하고 실제 UI의 만료 정책은 유지했다. 라우터266·경계/전달40·브라우저29·전체34,999 회귀의 문서 외 준비 명령4,055건 보존을 확인했다. 법령 검사에는 기존 정책 기대 차이1개를 별도 기록했다.
- [x] T076 기존 문제6 및 신규24의 최종 사용자 표시 기준 독립 흐름 검수를 마쳤다. 최초 신규24는 적절15·오류7·검토2, 실제 표시 기준 중간 재검수는 적절12·오류7·검토5였다. 전달 보강 후29건 적절/1건 오류에서 마지막 조건 모호점을 고치고1건 재검수·이전29건 유지 확인을 받아 최종30건 적절을 기록했다. `rag-boundary-hardening-20261115/REPORT_KO.md`와 CSV에 원본·중간·최종을 분리했다. 601건 전체를 새로 의미 검수하거나 새 답변을 생성한 것은 아니다. 실시간 앱 LLM/API·RDS·메인 관제 통합은 별도다.

### 재개 후 후속 검증 — 신규 질문과 실제 답변 결속 (2026-11-15)

- [x] T077 코드 수정 전 별도 작성한 CONT-001~024를 실제 Kiwi로 분석하고 Luna 배치 해석·문서 검색을 연결했다. 최초 흐름 적절14·오류8·검토2와 중간 적절23·검토1, 수정 후24건 적절을 분리 보존했다. 마지막1건 재검수와 나머지23건 유지 검사를 기록했다.
- [x] T078 복합 요청의 기능 한계를 세션 후속 상태에도 보존하고, 모델이 가능한 문서 부분만 임의로 실행하지 않도록 범위 선택을 받는다. 공란의 실제 원인과 일반 문서 설명의 경로, 모르는 신고, 보고서 별지 출처, 제목만 확보된 자료, 현장 부품 선정, 직접 차단의 사용자 안내를 보강했다.
- [x] T079 양식·작성 샘플 미확보를 각각 기록하고, 화재 질문은 검색된 시행규칙에 명시된 시행령 참조만 한 번 따라간다. 통지 지연 면제를 추정하지 않는다. 근거 후보9건을 실제 Luna 답변 작성·독립 검수하여 최종 요약7·원문2를 전달했다. 검수상 완료7·부분2이며, 인용 숫자 결속·원문 형식·기본 기록의무 누락 때문에 보류·수정한 원본도 남겼다. 수정하지 않은6건은 패킷 동일성을 재검증했다.
- [x] T080 라우터266·새 경계/제약15·기존 경계40·브라우저24·기존 연결13·정책 반영 법령216, 전체34,999의 문서 외 준비 명령4,055건 보존을 확인했다. 검색 인용177구간과 전달 인용55구간을 대조했다. `rag-continuation-20261115/REPORT_KO.md`, CSV, 검수 답변 MD에 최초/후속/최종 결과를 분리했다. 새24건의 수정 후 통과는 독립 신규 정확도가 아니며 실시간 앱 API·RDS·메인 통합 완료로 표시하지 않는다.

### 새 표현 대조와 근본 원인 분석 — 운영 코드 미수정 (2026-11-15)

- [x] T081 현행 모듈을 고정하고 새48개를 실제 Kiwi와 Luna 배치 해석으로 실행했다. 동일 의미12쌍·의미 변경12쌍을 구분하고, 기대는 정답으로 간주하지 않았다. 첫 독립 흐름 검수 적절25·오류15·추가검토8을 그대로 보존했다. 검색 found22개는 답변 완료가 아니며 이번22개 새 답변을 작성한 것은 아니다.
- [x] T082 형태소 제거 비교48개 중 route 변화1개, 원문/요약 역할 분리 실패3개, 전문14구간 중1구간만으로 원문 전달 관문 통과, 의미 역전 요약의 기계 검사 통과 및 독립 검수 없는 전달 차단을 격리 fixture로 재현했다. 고의 초안은 실제 서비스에 전달하지 않았다. 작성자의24쌍 대조 검수는 일관12·문제7·검토5로, 독립 정확도와 구분했다.
- [x] T083 인식 실패와 범위 밖의 혼동, 문자열 조건 재투영, 참고 조문/검색 목표의 역할 혼동, 요청별 coverage·출력 완전성 관문을 구조 감사와 실행 증거로 정리했다. 기존305 승인 recipe 재사용 경계와 공통 문서 요청 계약 보강 순서를 제안했다. `rag-root-cause-20261115/REPORT_KO.md`, 구조 감사, CSV·JSON을 저장했다. 표현별 패치·새 운영 요청 계약·303/305 통합은 이번 분석에서 적용하지 않았다.

### 후속 승인 — 오류 개선과 독립 신규 질문 재시험 (2026-11-15)

- [x] T064 최초 코드·실패·기대를 보존하고 새 질문 48개를 코드 튜닝 전에 생성했다. 기존 473건과 신규 48건을 구분하여 실제 Kiwi와 같은 실행 경로로 준비했다.
- [x] T065 `document-intent.js`에 좁은 일반 설명/개별 적용/보고 절차/잔여 표현을 분리했다. `law-evidence-search.js`에서 완료보고 근거와 공개 항목의 선택적 범위 확인을 보강했다. 초기 넓은 직행의 위험은 결과를 보존하고 버전 2로 좁혔다.
- [x] T066 `answer-contract.js`에 코드 원문 인용 ID·관련 근거·숫자/절차·원문/요약·독립 의미 검수와 초안 결속을 추가했다. 운영 모델 API나 RDS 실행기는 추가하지 않는다.
- [x] T067 기존 473+신규 48+동결 후 신규 32의 총 553건을 실제 분류·Luna 해석·문서 검색으로 추적했다. 답변 제안 159건 전부 독립 검수하고 수정 30건·추가 수정 3건을 재검수했다. 최종 요약 139/원문 5/근거 제한 8을 구분하고 생성문 4건은 보류했다. 부족 자료·조건 대기·보류는 정답 완료가 아니다.
- [x] T068 전체 34,999건 회귀에서 문서 외 기존 준비 명령 4,055건의 도구·조건을 보존했다. 라우터 266·답변 계약 31·해석/가드 22·기존 연결 13·브라우저 31/10/11 검사를 확인했다. 법령 검색은 정책 변경 기대 1개를 보존하고 새 정책 기준 216개를 확인했다. 신규 흐름 초기 69적절/6오류/5검토와 수정 회귀 74적절/6검토를 구분하고 `rag-improvement-20261115/REPORT_KO.md` 및 CSV에 기록했다. 메인 관제 실시간 모델 통합 완료가 아니다.
