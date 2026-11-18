# Tasks: K-TMS ML-ready 계약 검사 단계

**Input**: `specs/a-platform/010-ml-ready-contract-check/` (spec, plan, research, data-model, contracts/check-interface.md, quickstart)

**Tests**: 포함한다(SC-001·SC-002가 표본 테스트로 확인, FR-016).

- [P]: 다른 파일이라 같이 해도 됨
- 🧑: **사람이 하는 작업**(`terraform plan/apply`, AWS 실행). 에이전트는 실행하지 않는다.

## Phase 1: Setup

- [X] T001 `services/tms-silver/pyproject.toml`의 `py-modules`에 `lambda_ktms_ml_ready_check`를 추가한다. 다른 줄은 바꾸지 않는다.
- [X] T002 [P] `.github/workflows/tms-silver.yml`에 루트 `tests/` 실행 단계(저장소 루트에서 `PYTHONPATH=src python -m pytest -q tests`)와 트리거 경로 `tests/**`를 추가한다 (R9, FR-020).

## Phase 2: Foundational (모든 스토리 공통)

- [X] T003 `services/tms-silver/lambda_ktms_ml_ready_check.py` 뼈대: `sys.path`에 `/opt` 추가(R2), 상수(실행 기록 경로 `silver2/_runs/ktms_ml_ready_check`, ML-ready 기록 경로, 기본 테이블, 메일 최대 10줄), 입력 정규화 함수 `parse_event(event) -> dict`(data-model §1 기본값, `mode`는 `observe`|`block`만 허용).
- [X] T004 같은 파일에 `evaluate(window_df, rng, expect_source=None, real_stacks=None) -> list[dict]`: 대상 범위 행만 골라 `ml_ready_check._format_checks`·`_rule_checks`를 부르고, 창 전체 원본 열로 `to_ml_ready`를 돌려 대상 범위만 `_recompute_checks`와 같은 규칙으로 비교(상수 `KEY`·`SOURCE_COLUMNS`·`SKIP_RECOMPUTE` import, 허용 오차 1e-4), 굴뚝 키 겹침. 각 항목 `{"kind": "format|rule|recompute|overlap", "text": …}` (R5, data-model §3). 형식 위반으로 컬럼 목록이 다르면 나머지 검사는 건너뛴다(C의 `check()`와 같음).
- [X] T005 [P] `services/tms-silver/tests/test_lambda_ktms_ml_ready_check.py` 표본 도구: `to_ml_ready`로 만든 정상 2일 + 앞뒤 여유 구간 표본, 범위 `DayRange`.

## Phase 3: US1 - 계약을 어긴 갱신이 그날 아침 알려진다 (P1) 🎯 MVP

**Independent Test**: 정상·위반 표본으로 `evaluate`와 문안 함수를 돌려 위반 표본만 항목·행 수·첫 행 키가 들어간 위반 문안이 나오는지 본다.

- [X] T006 [P] [US1] 테스트: 정상 표본 위반 0, 범위 첫 행(00:00)과 마지막 날 끝 1시간 라벨 빈 값이 위반 아님(FR-004·005, SC-001), 변조 5종(컬럼 누락, 출처 섞임, 키 중복, 라벨 변조, Feature 변조) 모두 위반(SC-002), C의 `check()`와 같은 표본·같은 행에서 같은 위반 문구가 나옴(R5 일치 확인).
- [X] T007 [P] [US1] 테스트: 문안 — 위반 제목 `[tms] K-TMS 계약 위반 - …`, 항목 순서 형식→규칙→재계산→겹침, 11건 이상이면 10줄 + `외 N건`, 범위·스냅샷·모드·기록 경로·다시 실행 명령 포함, 대상 행 0이면 `empty` 문안(contracts §4).
- [X] T008 [US1] `lambda_ktms_ml_ready_check.py`에 `format_alert(result) -> (subject, message)` 구현 (R7, contracts §4).
- [X] T009 [US1] 같은 파일에 범위·스냅샷 결정 `resolve_target(args, ml_ready_job_run_id, s3)`: Job ID가 있으면 `silver2/_runs/ktms_ml_ready/*_<id>.json`에서 `range`·`snapshot_id`(범위 출처 `ml_ready_run`), 없으면 입력 날짜·auto를 `ktms_pipeline.resolve_range`로, 스냅샷은 `$snapshots` 최신 (R3).
- [X] T010 [US1] 같은 파일에 `read_window(table, snapshot_id, lo, hi, workgroup)`: awswrangler `athena.read_sql_query(…, ctas_approach=False)`로 `FOR VERSION AS OF` + `measured_at BETWEEN` 조회, 창은 `ktms_pipeline.ml_ready_window` (R4).
- [X] T011 [US1] 같은 파일에 `handler(event, context)`: 입력 → 범위·스냅샷 → 창 읽기 → `evaluate` → 실행 기록 쓰기(`ktms_pipeline.write_run_record`, data-model §4, 실패도 기록 후 다시 raise) → 출력(data-model §2).
- [X] T012 [P] [US1] 테스트: `handler`를 가짜 S3·가짜 조회 함수로 돌려 기록 키·필드, `range_source`, 실패 시 기록 후 예외 확인. `resolve_target`이 ML-ready 기록에서 범위·스냅샷을 가져오는지 확인.
- [X] T013 [US1] `infra/stacks/tms-silver/variables.tf`에 `ktms_check_mode`(observe|block, 기본 observe, validation)와 `pandas_layer_arn`(AWS SDK for pandas Python 3.12 관리형 레이어 ARN) 추가.
- [X] T014 [US1] `infra/stacks/tms-silver/ktms_check.tf`: 규칙 zip 레이어(`data.archive_file.package` 재사용), 진입점 zip(`lambda_ktms_ml_ready_check.py` + `ktms_pipeline.py`), 로그 그룹(14일), Lambda(3.12, 2048MB, 300초, 레이어 2개, 환경 변수: 버킷·워크그룹), 역할·정책(R6 표 그대로, 테이블 쓰기 없음).
- [X] T015 [US1] `infra/stacks/tms-silver/ktms_pipeline.asl.json`: `MlReady` 다음 `Check`(Lambda 호출, 재시도 1회, Catch → `CheckFailed`), 결과 Choice(`passed` → Done, `violation`/`empty` → 알림 → 모드에 따라 Done/Failed), `NotifyCheck`(Lambda가 준 제목·본문 발행), `CheckFailed` 알림(contracts §4 실행 실패 문안) → 모드에 따라 Done/Failed (data-model §2 전이).
- [X] T016 [US1] `infra/stacks/tms-silver/ktms.tf`: 상태 머신 템플릿 변수(`check_function`, `check_mode`) 추가, SFN 역할에 검사 Lambda `lambda:InvokeFunction` 추가.
- [X] T017 [US1] `terraform fmt -recursive`, `terraform validate` (에이전트, WSL `/mnt/c/terraform/terraform.exe`). ASL JSON 문법 확인.

## Phase 4: US2 - 운영 데이터와 운영 알림에 영향 없이 시험한다 (P1)

**Independent Test**: `stage=check`, `notify=false`로 실행해 Glue 미실행, 메일 0, 기록만 생김, 스냅샷 불변.

- [X] T018 [US2] `ktms_pipeline.asl.json`: `Defaults`에 `notify: true`, `check_table`, `expect_source: null`, `real_table: null` 추가, `RouteStart`에 `stage=check` → `Check`, 알림 단계 앞 `notify` Choice(false면 발행 없이 모드 분기).
- [X] T019 [P] [US2] 테스트: `parse_event`가 `notify`·`stage`·합성 입력 기본값을 채우고 잘못된 `mode`를 거부하는지, Lambda 정책 문서에 테이블 쓰기(`silver2/ktms_ml_ready/*` Put/Delete)가 없는지(Terraform 정책을 문자열로 읽어 확인).
- [X] T020 🧑 [US2] quickstart §2: 관리형 레이어 ARN 확인.
- [X] T021 🧑 [US2] quickstart §3: `terraform plan` 확인(추가: Lambda·레이어·역할·로그 그룹 / 변경: 상태 머신·SFN 역할 / 테이블·스케줄 변경 없음) 후 `apply`.
- [X] T022 🧑 [US2] quickstart §4: 검사만·알림 없음 실행 → Check만 실행, 메일 0, 기록 `passed`, 스냅샷 불변 (SC-004).
- [X] T023 🧑 [US2] quickstart §5: 없는 테이블로 실행 실패 알림 제목·본문 확인, 관찰 모드라 실행 성공.

## Phase 5: US3 - 학습하는 사람이 믿을 수 있는 버전을 고른다 (P2)

- [X] T024 [US3] `specs/a-platform/008-ktms-silver-pipeline/contracts/ktms-tables.md`에 "검사를 통과한 스냅샷 읽기" 절 추가: 마지막 `passed` 기록 찾기(S3 목록 또는 Athena로 `_runs` 조회 예시), 그 `snapshot_id`로 Athena·Spark 시간 여행 (FR-018, data-model §5).
- [ ] T025 🧑 [US3] quickstart §6: 매일 실행 7번 관찰(위반 메일 0, 기록 7개 `passed`, 소요 시간) (SC-001, SC-005). 이상 없으면 §7 차단 모드 전환.

## Phase 6: US4 - 같은 검사를 합성 테이블에도 쓴다 (P3)

- [X] T026 [US4] `handler`: `expect_source`를 `evaluate`에 넘기고, `real_table`이 있으면 같은 범위 `stack_code`만 Athena로 읽어 겹침 검사에 쓴다.
- [X] T027 [P] [US4] 테스트: `expect_source=ktms_synth`인데 출처 `ktms` → 위반, 실데이터 굴뚝 키 겹침 → `[겹침]` 위반.

## Phase 7: Polish

- [X] T028 `services/tms-silver/README.md`에 검사 단계(수동 실행 명령, 모드, 기록 위치) 한 절 추가.
- [X] T029 `ruff check`, 서비스 테스트·루트 테스트 전체 실행.
- [ ] T030 C에게 `check()` 범위 인자 제안(R5 후속), E에게 통과 스냅샷 안내 공유(US3).
- [ ] T031 spec Status 갱신, 아키텍처 그림(전체·통합)에 계약 검사 단계 반영.

## Dependencies

- Setup → Foundational(T003~T005) → US1(T006~T017) → US2(T018~T023) → US3·US4 → Polish
- US2의 사람 작업(T021~T023)은 US1·US2 코드가 끝난 뒤 한 번에 apply한다. 매일 스케줄이 켜져 있으므로 **관찰 모드로만** 배포한다.
- US4(T026·T027)는 합성 테이블이 생기기 전에 해 둘 수 있지만, 실제 실행은 합성 통합 작업에서 한다.

## Parallel Examples

- T001 ∥ T002 ∥ T005
- US1: T006 ∥ T007 ∥ T012(테스트 먼저) → T008~T011 → T013~T016 → T017
- US2: T018 ∥ T019

## Implementation Strategy

- MVP = US1 + US2 코드(T001~T019). 함께 배포해야 운영 무영향 시험이 가능하다.
- 배포 후 관찰 7일(T025) → 차단 모드.
- US4는 합성 데이터 통합 PR에서 실제로 쓴다.
