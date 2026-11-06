# Tasks: 대만 CEMS Silver 정제

**Input**: [spec.md](spec.md), [plan.md](plan.md) | **Updated**: 2026-11-06

**Tests**: 포함한다 (spec의 FR-017, FR-018이 같은 결과와 pandas·Spark 일치를 요구한다).

## Format: `[ID] [P?] [Story] 설명`

- **[P]**: 서로 다른 파일이라 병렬로 할 수 있음
- **[Story]**: 해당 사용자 스토리 (US1~US4)
- 완료는 `[x]`, 남음은 `[ ]`

## Phase 1: Setup

- [x] T001 `src/smokestack_guard/silver/`, `tests/` 구조 만들기
- [x] T002 월별 원본 JSONL 확보 (S3 `bronze/tw_cems/historical/`, 로컬 2023-11~2026-10)

## Phase 2: Foundational

- [x] T003 항목 매핑·허용 코드·컬럼 상수 정의 `src/smokestack_guard/silver/tw_cems.py`
- [x] T004 원본 정리 `prep`: 시각 `ISO8601` 파싱(`T`/공백, 초 유무), 숫자 변환, 문자열 축소 `tw_cems.py`

## Phase 3: US1 — 30분 측정 테이블 (P1)

**Goal**: 모든 항목의 30분 값을 `status`와 함께 조회한다.

- [x] T005 [US1] `to_silver`: 슬롯 변환과 `status` 5종 `tw_cems.py`
- [x] T006 [US1] 완전 중복 제거, 같은 시각 값 충돌 처리 `tw_cems.py`
- [x] T007 [US1] `ratio` 계산, `flag_code_ratio_mismatch` `tw_cems.py`
- [x] T008 [US1] 단위 테스트 (짝, 혼합 코드, `other_code`, 부분, 충돌, 기준값 변경·없음, 단위, 시각 형식, 청크 분할) `tests/test_silver.py`
- [x] T009 [US1] 월 단위 `build`와 CLI `tw_cems.py`
- [x] T010 [US1] 36개월 전체 실행. 슬롯 수 8,036만 = `status` 5종 합계 (SC-001)
- [ ] T011 [US1] 월별 단계별 행 수(입력 → `status`별) 기록 (FR-016, SC-006)

## Phase 4: US2 — ML 학습용 데이터 (P2)

**Goal**: Silver만으로 분류·회귀 학습을 시작한다.

- [x] T012 [US2] Feature 생성(Lag, 변화량, 이동통계, 추세, 시간 주기) `src/smokestack_guard/silver/ml_ready.py`
- [x] T013 [US2] 정답과 `classification_eligible`/`regression_eligible`, 버전 컬럼 `ml_ready.py`
- [x] T014 [US2] 모델 대상 선택 `ok` · `nox`/`sox` · `ppm` `ml_ready.py`
- [x] T015 [US2] 단위 테스트 (정답 방향, 빈 구간 비연결, 추세 값, 현지 시각, 대상 선택) `tests/test_silver.py`
- [x] T016 [US2] 36개월 ML-ready 생성 (1,769만 행, 학습 가능 양성 135,978행)
- [ ] T017 [US2] 실데이터에서 Feature가 미래 값을 쓰지 않았는지 표본 검증 (SC-003)
- [ ] T018 [US2] 정답이 t+60 실측과 일치하는지 표본 1,000행 대조 (SC-004)
- [ ] T019 [US2] 월별 양성 수 기록 (SC-006)
- [ ] T020 [US2] 도은 님과 Feature 목록·정답·제외 조건 승인, 학습 입력 확인 (SC-008)

## Phase 5: US3 — 시간 의미 검증 (P3)

- [x] T021 [US3] 1시간 자료(AQX_P_187, 2025-10)와 15분 평균 비교: 시작 해석 100% 일치 (SC-007)
- [x] T022 [US3] 결론을 문서에 기록 (spec US3, 변환 규칙 문서)

## Phase 6: US4 — Glue에서 같은 결과로 실행 (P2)

**Goal**: 월 단위 원본을 Glue로 변환해 pandas와 같은 Silver를 얻는다.

- [x] T023 [US4] Spark 구현 `src/smokestack_guard/silver/tw_cems_spark.py`
- [x] T024 [US4] 패리티 단위 테스트 `tests/test_silver_spark.py` (Docker, Spark 3.5.4)
- [x] T025 [US4] 실데이터 패리티 스크립트와 샘플 3개 달 검증 `scripts/validate_spark_parity.py`
- [x] T026 [US4] 동적 파티션 덮어쓰기 확인 (다른 달 유지, 같은 달만 교체)
- [x] T027 [US4] Glue 작업 스크립트 `scripts/glue_tw_cems_silver.py`
- [x] T028 [US4] 실행 환경·방법 문서 `spark_migration_checklist.md`
- [ ] T029 [US4] S3 출력 위치와 최소 IAM 권한 확정, Glue 작업·권한을 Terraform으로 생성 (A 담당, 적용은 사람이)
- [ ] T030 [US4] Glue에서 한 달 전체 실행 후 pandas 결과와 비교 (SC-009)
- [ ] T031 [US4] 실행 시간·DPU 비용 측정 후 A에게 공유
- [ ] T032 [US4] 36개월 Glue 실행
- [ ] T033 [US4] (선택, 낮은 우선순위) ML-ready Spark 이식

## Phase 7: Open Questions (spec 참고)

- [ ] T034 기준 변경 처리 결정: Feature 창 안의 기준 변경 표시·제외 (OQ1, 팀 논의)
- [ ] T035 음수·극단값 처리 방침 (OQ2)
- [ ] T036 `NB`/`AA` 코드의 학습 포함 여부: 코드별 양성 손실률 분석 후 결정 (OQ3)
- [ ] T037 산소 보정과 `std` 일치, K-TMS와의 측정 기준 비교의 공식 근거 확인 (OQ4)

## Phase 8: 마무리

- [x] T038 spec·plan·tasks를 현재 구현에 맞게 현행화
- [ ] T039 2023-11(11-27 16:30 이후), 2023-12(첫 6시간 반) 원본 공백의 재다운로드 여부 결정
- [ ] T040 PR #17(계약 정렬)·PR #19(Spark 이식) 리뷰와 머지

## Dependencies

- US1 → US2 (ML-ready는 Silver를 입력으로 한다)
- US1 → US4 (Spark는 pandas 결과를 기준선으로 비교한다)
- US3은 독립이며 완료되어 경계 정의의 근거가 되었다
- T029 → T030 → T032 (출력 위치·권한이 있어야 Glue 실행 가능)
- T034~T037은 모델 학습(E) 전에 결정되어야 한다
