# Tasks: 학습용 합성 K-TMS 데이터 AWS Bronze 적재

**Input**: `specs/a-platform/011-synthetic-train-s3-ingest/` (spec, plan, research, data-model, contracts/ingest-interface.md, quickstart)

**Tests**: 포함한다(SC-002·SC-005가 자동 테스트로 확인, 바이트 일치·실측 경로 거부).

- [P]: 다른 파일이라 같이 해도 됨
- 🧑: **사람이 하는 작업**(`terraform plan/apply`, AWS 실행, 파일 업로드). 에이전트는 실행하지 않는다.
- ⏳: C의 `read_bronze` 경로 인자 머지를 기다림

## Phase 1: Setup

- [X] T001 [P] `.github/workflows/tms-synthetic-train.yml` 추가: `k_tms_synthetic_train/**`·워크플로 변경 시, Python 3.12, `pip install pandas numpy pyyaml pytest`, `working-directory: k_tms_synthetic_train`에서 `python -m pytest -q` (research R10).
- [X] T002 [P] `.github/CODEOWNERS`에 `/k_tms_synthetic_train/ @olchangiagi @SungChul23`, `/infra/stacks/tms-synthetic/ @SungChul23` 추가.
- [X] T003 `infra/stacks/tms-synthetic/`에 `backend.tf`(키 `stacks/tms-synthetic/terraform.tfstate`), `versions.tf`(`~> 1.15.0`, aws `~> 6.0`, archive, `default_tags` stack=`tms-synthetic`), `variables.tf` 뼈대, `outputs.tf` 생성. 다른 스택 구조를 따른다.

## Phase 2: Foundational (진입점 공통)

- [X] T004 `k_tms_synthetic_train/lambda_handler.py` 뼈대: 설정 로드(`config/daily.json`이 있으면 json, 없으면 `plan.load_config("config/daily.yaml")` — 로컬 테스트용), 참조 통계 로드(S3 `tms_synthetic_train/_ref_stats/<stats_version>.csv` → `/tmp`, 전역 캐시, 파일 안 `stats_version` 열과 설정 값이 다르면 실패, R7), 입력 정규화 `parse_event`(mode `regular`|`backfill`|`check`, DLQ 본문의 `requestPayload` 풀기, 날짜 검증, 백필 31일 상한, data-model §2).
- [X] T005 같은 파일에 `day_snapshots(config, ref_df, day)`: `daily.episodes_started_on(day−1) + (day)` → `pack.pack_day(config, eps, day)`, 결과를 날짜별로 실행 안에서 캐시(R2). 
- [X] T006 [P] `k_tms_synthetic_train/tests/test_lambda_handler.py` 도구: 가짜 S3(`put_object`, `get_object`, `head_object`(없으면 404 ClientError), `get_paginator`), 테스트용 설정(`tests/conftest.py`의 설정·표본 통계 재사용).

## Phase 3: US1 - 30분마다 실측처럼 쌓인다 (P1) 🎯 MVP

**Independent Test**: 가짜 S3에 정기 실행을 돌려 슬롯 폴더·파일 4개·순서, `_SUCCESS` 건너뛰기, 실측 경로 거부, 파일 모드(`generate.generate_day`)와 바이트 일치를 확인.

- [X] T007 [P] [US1] 테스트: `regular`(예정 시각 10:10 KST) → 측정 09:00 슬롯 `run_ts=…T011000Z` 하나만 씀, 180분 창 안의 빈 슬롯 함께 채움, `_SUCCESS` 있는 슬롯 건너뜀, 자정 걸침(00:10 KST → 전날 슬롯), 쓰기 순서(데이터 2개 → manifest → `_SUCCESS`), 같은 날짜를 `generate.generate_day`로 로컬에 쓴 파일과 바이트 일치(SC-002), `_manifest/<날짜>.jsonl` 한 번만 쓰고 내용이 로컬 결과와 같음.
- [X] T008 [US1] `lambda_handler.py`에 `due_slots(now, lookback)`·`write_slot(s3, bucket, slot, info)`(head `_SUCCESS` → 없으면 `snapshot.make_files` + `s3_sink.write_files_s3`)·`write_manifest(s3, bucket, config, day)`(`generate.manifest_row`, 없을 때만)·`run_regular` 구현 (R4, FR-001~007).
- [X] T009 [US1] 같은 파일 `handler(event, context)`: 모드 분기, 출력 한 줄 JSON(data-model §3), 값은 로그에 남기지 않음.
- [X] T010 [P] [US1] 테스트: 진입점이 `confluent_kafka`·`publish`·`release`·`cycle`을 import하지 않음(`sys.modules` 확인), `writer.check_prefix`가 `tms_cleansys/` 경로를 거부(SC-005).
- [X] T011 [US1] `infra/stacks/tms-synthetic/main.tf` 코드 zip: `archive_file`에 `lambda_handler.py`, research R3의 모듈 목록, `config/daily.json`(= `jsonencode(yamldecode(file(daily.yaml)))`)을 `source` 블록으로. 
- [X] T012 [US1] 같은 파일: 로그 그룹(14일), 역할·정책(research R6 표 그대로), Lambda(python3.12, 1024MB, 900초, 레이어 `pandas_layer_arn`, 환경 변수 `BUCKET`·`ALERT_TOPIC_ARN`), 정기 스케줄 `cron(10,40 * * * ? *)` Asia/Seoul, 유연 시간 창 OFF, 입력 `{"mode":"regular","scheduled_time":"<aws.scheduler.scheduled-time>"}`, 상태 `synthetic_schedule_enabled ? ENABLED : DISABLED`.
- [X] T013 [US1] `variables.tf`: `raw_bucket_name`, `pandas_layer_arn`(010과 같은 기본값), `alert_topic_name`(`tms-collector-alerts`), `synthetic_schedule_enabled`(기본 false), 모두 description·type.
- [X] T014 [US1] `terraform fmt -recursive`·`validate` (에이전트, WSL `/mnt/c/terraform/terraform.exe`).

## Phase 4: US2 - 놓친 슬롯은 알려지고 다시 채운다 (P1)

**Independent Test**: 가짜 S3로 점검 모드가 빈 슬롯을 찾고 알림 문안을 만드는지, DLQ 두 모양의 입력이 같은 실행으로 풀리는지.

- [X] T015 [P] [US2] 테스트: `check`(어제 48개 중 2개 없음) → 빈 `run_ts` 2개, SNS 제목 ASCII `[tms] synthetic train missing slots - <day> (46/48)`, 본문에 목록과 `backfill` 재실행 명령. 다 있으면 발행 없음. DLQ 본문 두 모양(Scheduler 원문, `requestPayload` 감싼 것) → 같은 입력.
- [X] T016 [US2] `lambda_handler.py`에 `run_check`(48슬롯 `_SUCCESS` head, 빈 목록, SNS 발행) 구현 (FR-013, contracts §4).
- [X] T017 [US2] `main.tf`: SQS `tms-synthetic-train-dlq`(일반, 보관 14일), `aws_lambda_function_event_invoke_config`(재시도 2, 최대 나이 3600, 실패 목적지 = DLQ), 정기 스케줄 `retry_policy`(3회, 3600초)·`dead_letter_config`(DLQ), 스케줄 역할(Invoke + SQS Send), DLQ 큐 정책, 점검 스케줄 `cron(0 6 * * ? *)` Asia/Seoul 입력 `{"mode":"check"}`, CloudWatch 알람 `tms-synthetic-train-dlq-not-empty`(`ApproximateNumberOfMessagesVisible` ≥ 1, 5분) → 운영 SNS (R5).

## Phase 5: US3 - 수집 시작일부터 채운다 (P1)

- [X] T018 [P] [US3] 테스트: `backfill` 이틀 → 날짜마다 48개, 이미 있는 폴더 건너뜀, `run_ts`가 미래인 슬롯은 쓰지 않음, 31일 초과 거부.
- [X] T019 [US3] `lambda_handler.py`에 `run_backfill` 구현 (FR-008).

## Phase 6: 배포와 운영 시험 (US1~US3, 사람)

- [X] T020 🧑 quickstart §2: 참조 통계 `ref-1030-1110.csv` 업로드(B 또는 A).
- [X] T021 🧑 quickstart §3: `tms-synthetic` plan(추가만) → apply. 스케줄은 꺼진 상태.
- [X] T022 🧑 quickstart §4·§5: 슬롯 하나 실행, 파일 확인, B 로컬과 바이트 비교 (SC-002).
- [X] T023 🧑 quickstart §6: 정기 스케줄 켜기, 다음 :10/:40 폴더 생성 확인.
- [X] T024 🧑 quickstart §7: 10-30 ~ 어제 백필, 점검으로 빈 슬롯 0 확인 (SC-003).
- [ ] T025 🧑 quickstart §8: 실패 시험 1건(DLQ·알람·재처리), 7일 관찰 (SC-001, SC-004).

## Phase 7: US4 - 합성 Silver·ML-ready·계약 검사 (P2)

**Independent Test**: 이틀 범위로 합성 갱신 → 두 합성 테이블, 출처 `ktms_synth`, 검사 통과, 실측 테이블 스냅샷 불변.

- [X] T026 [P] [US4] `services/tms-silver/glue_ktms_ml_ready.py`에 `--data_source`(기본 없음 = 자동) 인자 추가, `ml_ready.to_ml_ready(silver, data_source=args.data_source)`로 전달, 실행 기록에 남김. 테스트 `services/tms-silver/tests/test_glue_ktms_ml_ready.py`에 인자 전달 확인 추가 (research R9).
- [X] T027 [US4] `infra/stacks/tms-silver/ktms_pipeline.asl.json`: 입력 `source`(`ktms` 기본 | `ktms_synth`)를 `Defaults`에 추가, `source`에 따라 Glue 인자(`--source_prefix`, `--silver_table`, `--ml_ready_table`, `--data_source`, `--runs_prefix`)와 검사 입력(`check_table`, `expect_source`, `real_table`)을 정하는 Pass 상태. 기존 실측 경로와 알림은 바꾸지 않음. `services/tms-silver/tests/test_ktms_asl.py`에 두 source 경로 테스트 추가.
- [X] T028 [US4] `infra/stacks/tms-silver/ktms.tf`: Glue 역할에 합성 원본 읽기(`tms_synthetic_train/ingest_date=*`)·합성 테이블 쓰기(`silver2/ktms_synth*/*`, `silver2/_runs/ktms_synth*/*`)·카탈로그 권한, 합성 매일 스케줄(03:30 KST, 입력 `{"source":"ktms_synth"}`, 변수 `ktms_synth_schedule_enabled` 기본 false). `ktms_check.tf`: 검사 Lambda에 합성 테이블·실행 기록 읽기 권한.
- [X] T029 [US4] `terraform fmt`·`validate`, 서비스 테스트 전체.
- [X] T029a [US4] `src/smokestack_guard/silver/ktms.py`의 `read_bronze`·`_keys`에 `prefix` 인자 추가(기본 `tms_cleansys/`, 기존 동작 그대로, `/`로 끝나야 함). 테스트 `tests/test_silver.py`에 합성 루트만 읽기·`to_silver` 통과 추가. **C 리뷰 필요**(원칙 IV, C 코드 변경).
- [ ] T030 🧑 [US4] (T029a 반영) `tms-silver` plan/apply → 상태 머신을 `{"source":"ktms_synth","start_date":"2026-10-30","end_date":"<어제>"}`로 실행(최대 일수 제한 시 나눠서) → 두 테이블 생성, 검사 통과, 실측 스냅샷 불변 확인 → 합성 스케줄 켜기.
- [X] T031 [P] [US4] `scripts/label_balance_queries.sql` 추가: 실측(`ktms_ml_ready`)과 합성(`ktms_synth_ml_ready`)을 `UNION ALL`로 합쳐 Athena에서 양성·음성 비율을 보는 쿼리 4개. 모두 `classification_eligible`(분류)·`regression_eligible`(회귀 행 수) 기준이고, 자리표시자 `{start}`·`{end}`(KST 측정일)와 선택 스냅샷(`FOR VERSION AS OF`)을 받는다.
  1. `balance_by_source`: `data_source` × `item_code`별 적격 행, 양성(`label_entry_60m = 1`), 음성, 양성 비율
  2. `balance_combined`: 성분별 실측 단독 vs 실측+합성 양성 비율과 양성 증가 배수(SC-007의 "약 2배" 확인)
  3. `synth_by_shape`: 합성 `stack_code`(`SYN-T-<날짜>-<성분>-<모양>-<번호>`)에서 모양을 꺼내 모양별 양성 수 — 희귀 모양(GRADUAL·OVER·PLATEAU)이 얼마나 보강됐는지
  4. `balance_by_day`: 측정일 × 출처별 양성 수 추이(합성이 매일 1:1로 들어오는지)
- [X] T032 [P] [US4] `infra/stacks/tms-eda`가 아니라 `tms-silver` 스택에 위 4개를 `aws_athena_named_query`(워크그룹 `tms-eda`, DB `tms_silver2`)로 등록해 콘솔 "저장된 쿼리"에서 바로 열게 한다. 쿼리는 실행하지 않는다(사람이 콘솔에서 실행).
- [ ] T033 ⏳🧑 [US4] 합성 ML-ready가 생기면 4개 쿼리를 콘솔에서 실행하고 결과(성분별 실측 단독·합친 양성 비율, 증가 배수, 모양별 합성 양성 수)를 spec Status와 E 공유 메모에 기록 (SC-007).

## Phase 8: US5 문서와 마무리

- [X] T034 [P] [US5] `AGENTS.md`: S3 경로 규칙에 `tms_synthetic_train/`(합성 적재 Lambda만 쓰기, `_manifest/`·`_ref_stats/`), 테이블 `ktms_synth`·`ktms_synth_ml_ready`, 저장소 구조에 `infra/stacks/tms-synthetic/`·`k_tms_synthetic*/`(+ 008·010·009 스택이 빠져 있으면 함께) 추가.
- [X] T035 [P] [US5] `specs/a-platform/008-ktms-silver-pipeline/contracts/ktms-tables.md`에 합성 테이블 절: 실측과 합치는 법, 평가에서 `data_source = 'ktms_synth'` 제외, 외부 검증은 참조 통계 기간(10-30~11-10) 이후.
- [X] T036 [P] `k_tms_synthetic_train/README.md`에 "AWS 운영" 절(Lambda·스케줄·백필·재처리 명령은 011 contracts 링크) 추가. B에게 공유.
- [ ] T037 spec Status 갱신, 아키텍처 그림(전체·통합·추론)에 합성 적재 경로 반영.

## Dependencies

- Setup(T001~T003) → Foundational(T004~T006) → US1(T007~T014) → US2(T015~T017) → US3(T018~T019) → 배포(T020~T025)
- US4 코드(T026~T029, T031·T032 쿼리)는 US1과 독립이라 언제든 가능. 실행(T030·T033)은 C 머지와 T024(백필) 뒤.
- US5 문서는 언제든.

## Parallel Examples

- T001 ∥ T002 ∥ T006
- US1: T007 ∥ T010(테스트 먼저) → T008 → T009 → T011~T013 → T014
- US4 코드: T026 ∥ T027 ∥ T031 → T028 → T032 → T029

## Implementation Strategy

- MVP = US1 + US2 + US3 코드(T001~T019)를 한 번에 배포(T021). 스케줄은 꺼진 채 시험 후 켬.
- US4 코드는 같은 PR에 넣되 스케줄은 꺼 두고, C 머지 후 실행.
