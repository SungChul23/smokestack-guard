# Tasks: 대시보드용 K-TMS 관측 RDS 적재

**Input**: `specs/a-platform/012-dashboard-rds-load/` (spec, plan, research, data-model, contracts/load-interface.md, quickstart)

**Tests**: 포함한다(SC-002 멱등, SC-005 상태 행 null, SC-008 권한이 자동 테스트로 확인).

- [P]: 다른 파일이라 같이 해도 됨
- 🧑: **사람이 하는 작업**(`terraform plan/apply`, AWS 실행, 베스천 터널, 파일 업로드). 에이전트는 실행하지 않는다.
- 📨: 다른 담당에게 받을 것이 있음

## Phase 1: Setup

- [ ] T001 [P] `services/dashboard-load/` 뼈대: `pyproject.toml`(Python 3.11+, 의존 `pandas`, `boto3`, `pg8000`, 개발 의존 `pytest`, `ruff`; 저장소 루트 `src/`의 `smokestack_guard`와 `services/tms-silver/ktms_pipeline.py`를 경로로 import), `README.md`(목적, 명령 4개, 접속 방식), `tests/conftest.py`.
- [ ] T002 [P] `services/dashboard-load/certs/global-bundle.pem`: RDS 공용 CA 번들(공개 인증서)을 받아 넣고 출처 URL을 README에 적는다 (research R4).
- [ ] T003 [P] `services/dashboard-load/build_layer.sh`: `pip install --target build/layer/python pg8000==<고정 버전>` → `build/pg8000_layer.zip`. `build/`는 `.gitignore`에 추가 (research R5).
- [ ] T004 [P] `.github/workflows/dashboard-load.yml`: `services/dashboard-load/**`, `src/smokestack_guard/silver/**`, `services/tms-silver/ktms_pipeline.py` 변경 시. Python 3.12, `ruff check`, PostgreSQL 16 서비스 컨테이너(`pgvector/pgvector:pg16`)로 `pytest -q`.
- [ ] T005 [P] `.github/CODEOWNERS`에 `/services/dashboard-load/ @SungChul23 @jaeyan42`, `/infra/stacks/tms-dashboard-load/ @SungChul23` 추가.
- [ ] T006 `infra/stacks/tms-dashboard-load/`에 `backend.tf`(키 `stacks/tms-dashboard-load/terraform.tfstate`), `versions.tf`(`~> 1.15.0`, aws `~> 6.0`, archive, `default_tags` stack=`tms-dashboard-load`), `variables.tf` 뼈대, `outputs.tf`.

## Phase 2: Foundational (DB 구조·접속, 모든 스토리의 전제)

- [ ] T007 `services/dashboard-load/migrations/001_schemas_roles.sql`: 스키마 `ref`·`obs`·`ops`·`app`·`rag`, `CREATE EXTENSION IF NOT EXISTS vector`, 계정 `tms_loader`·`tms_app`(`LOGIN`, `GRANT rds_iam`), 스키마 사용 권한 (data-model §7).
- [ ] T008 `migrations/002_ref.sql`: `ref.site`, `ref.site_name_map`, `ref.stack`(`source`, `first_seen`), 뷰 `ref.v_stack`(현재 유효한 이름 이력으로 `site_id`), `ref.status_code` + 고정값 9행 (data-model §4). 권한: `tms_loader` 읽기 + `ref.stack` INSERT, `tms_app` 읽기.
- [ ] T009 `migrations/003_obs_ops.sql`: `obs.measurement_30m`(PK `(stack_key, item, measured_at)`, 인덱스 `(measured_at)`), `obs.daily_stack_summary`, `obs.daily_national_summary`, `ops.schema_migrations`, `ops.load_run`, `ops.mapping_report`, `ops.unmapped_name` (data-model §1~3·§5). 권한: `tms_loader` 읽기·쓰기, `tms_app` `obs` 읽기.
- [ ] T010 `migrations/004_app_rag.sql`: D 제안의 `app.*`, `rag.doc_chunk`(`vector(1024)`, GIN, HNSW) 구조만. 권한: `tms_app` `app` 읽기·쓰기·생성, `rag` 읽기 (data-model §6).
- [ ] T011 `services/dashboard-load/db.py`: `connect(host, port, user, iam=True|password=…)` — IAM 토큰(`boto3 rds.generate_db_auth_token`), TLS(`certs/global-bundle.pem` 검증), pg8000. 관리자 비밀번호 접속은 터널용 경로로만.
- [ ] T012 [P] `tests/test_migrations.py`: 빈 PostgreSQL에 001~004 적용 성공, 두 번 적용해도 오류 없음(`ops.schema_migrations`로 건너뜀), `ref.status_code` 9행.
- [ ] T013 `services/dashboard-load/run_dashboard_load.py migrate [--dry-run]`: `migrations/*.sql` 번호순, 미적용만, 파일마다 트랜잭션, `ops.schema_migrations` 기록. 접속은 `localhost:5433` + `tms_admin`(비밀번호는 실행 시 Secrets Manager에서 읽음, 출력·저장하지 않음) (research R8).

## Phase 3: US1 - 오늘 값까지 30분 안에 보인다 (P1) 🎯 MVP

**Independent Test**: 가짜 S3 스냅샷 + PostgreSQL 컨테이너로 `recent`를 돌려 최신 칸 생성, 두 번 실행 시 동일, 며칠 전 칸 정정 반영, 상태 행 null, `_SUCCESS` 없는 폴더 무시를 확인.

- [ ] T014 [P] [US1] `tests/test_load.py`: `prepare_rows(silver_df)` — NOx·SOx만, `stack_key = 지역|사업장|번호`(ML-ready `ml_ready.py`의 합치는 규칙과 같은지 같은 입력으로 비교), `status`→`status_code`, 상태 행 `value` null(SC-005), `ratio_pct = ratio × 100`, 알 수 없는 상태 문자열이면 예외.
- [ ] T015 [P] [US1] `tests/test_load.py`: `recent_range(now, hours)` → 수집 시각 범위와 `ingest_date` 목록(자정·UTC 경계), `_SUCCESS` 없는 폴더는 `read_bronze`가 건너뜀(008 테스트 표본 `services/tms-silver/tests/ktms_cases.py` 재사용).
- [ ] T016 [US1] `services/dashboard-load/load.py`: `recent_range`, `read_recent(s3, bucket, lo, hi)`(C의 `read_bronze` + 수집 시각 필터 + `to_silver`, 수정 없이 호출), `prepare_rows`, `new_stack_keys(rows, known)`.
- [ ] T017 [P] [US1] `tests/test_db.py`: `upsert_measurements` — 새 행 삽입, 같은 값 재적재 시 `unchanged`(SC-002, `loaded_at` 유지), 값·상태가 바뀌면 덮어씀, 사흘 전 측정 시각도 갱신(US1-3), `ref.stack`에 새 키를 `source=observed`로 추가.
- [ ] T018 [US1] `db.py`에 `upsert_measurements(conn, rows, load_path)`(임시 표 → `INSERT … ON CONFLICT … DO UPDATE … WHERE … IS DISTINCT FROM`, 1만 행 단위), `add_stack_keys`, `record_run`(`ops.load_run`) (research R5).
- [ ] T019 [US1] `services/dashboard-load/lambda_handler.py`: 입력 검증(contracts §1), `mode=recent` → 읽기·정리·UPSERT·실행 기록, 응답 한 줄 JSON(contracts §3). 비밀값·원문은 로그에 남기지 않는다.
- [ ] T020 [P] [US1] `tests/test_handler.py`: 입력 검증(모르는 mode, `day`에 날짜 없음), `db_host` 없으면 실패, 응답 모양.
- [ ] T021 [US1] `infra/stacks/tms-network/security_groups.tf`: 보안그룹 `tms-loader`(나가는 5432 → `tms-db`, 443 → S3 접두사 목록), `tms-db` 들어오는 5432 ← `tms-loader` (research R6). 추가만.
- [ ] T022 [US1] `infra/stacks/tms-database/main.tf`: `iam_database_authentication_enabled = true` (research R4).
- [ ] T023 [US1] `infra/stacks/tms-dashboard-load/main.tf`: 코드 zip(`lambda_handler.py`, `load.py`, `db.py`, `certs/`, `ktms_pipeline.py`), 레이어 3개(관리형 pandas 레이어 ARN, 기존 `tms-smokestack-guard-rules` 최신 버전 data source, `build/pg8000_layer.zip`), Lambda(python3.12, 1024MB, 300초, VPC 앱 서브넷 2개 + `tms-loader`, 환경 변수 `BUCKET`·`DB_USER=tms_loader`), 역할(plan IAM 표 그대로, `AWSLambdaVPCAccessExecutionRole`), 로그 그룹 14일.
- [ ] T024 [US1] `infra/stacks/tms-dashboard-load/state_machine.tf`: 상태 머신 `tms-dashboard-load`(Standard, contracts §2: CheckDb → Load → Notify, Catch → SNS → Fail), 역할, Scheduler `cron(15,45 * * * ? *)` Asia/Seoul 입력 `{"mode":"recent"}`, 상태 `load_schedule_enabled ? ENABLED : DISABLED`, 스케줄 역할.
- [ ] T025 [US1] `variables.tf`: `raw_bucket_name`, `pandas_layer_arn`(010과 같은 기본값), `alert_topic_name`(`tms-collector-alerts`), `load_schedule_enabled`(기본 false), `recent_hours`(기본 4). 모두 description·type.
- [ ] T026 [US1] `terraform fmt -recursive`·`validate` 세 스택 (에이전트, WSL `/mnt/c/terraform/terraform.exe`).

## Phase 4: US3 - 굴뚝을 사업장 코드·좌표와 연결한다 (P1)

**Independent Test**: 표본 사업장 목록으로 `load-ref`를 돌려 `ref` 세 표가 채워지고, 다시 돌려도 같으며, 이름 이력 한 줄 추가로 옛 이름 관측이 같은 `site_id`로 조회되는지.

- [ ] T027 📨 [US3] D에게 사업장 목록 요청(contracts §4 컬럼, 한 줄 = 굴뚝 하나). 받으면 🧑 원본 버킷 `ref/sites/<버전>.csv`에 올린다(저장소에 넣지 않음, research R9).
- [ ] T028 [P] [US3] `tests/test_ref.py`: 표본 CSV(가짜 이름) → `ref.site`·`ref.site_name_map`(`confirmed_by=auto|사람`)·`ref.stack`(`source=site_list`), 같은 `site_id`인데 사업장 정보가 다르면 거부, 두 번 적재 시 동일, 이름 이력 추가 후 `ref.v_stack`이 옛·새 이름 키 모두 같은 `site_id`.
- [ ] T029 [US3] `run_dashboard_load.py load-ref --sites <s3://… | 로컬> [--dry-run]` + `db.py`의 `load_ref` 구현 (contracts §4).

## Phase 5: US2 - 일일 요약과 매핑 점검 (P1)

**Independent Test**: PostgreSQL에 관측 표본을 넣고 `daily`를 돌려 요약 값이 직접 계산과 같고, 관측 행 변화 0, 처음 본 이름만 돌려주는지.

- [ ] T030 [P] [US2] `tests/test_db.py`: `refresh_daily_summaries(conn, days)` — 48칸 중 정상 40·미수신 5·행 없음 3 사례(US2-3), `ok` 0칸이면 통계 null, 기준값 범위, 전국 최고값 동률 규칙, 관측 행 변화 0(SC-003 후반).
- [ ] T031 [P] [US2] `tests/test_db.py`: `summary_days(conn, today)` = 최근 2일 + 직전 `daily` 이후 `loaded_at`이 바뀐 날짜 (FR-009).
- [ ] T032 [P] [US2] `tests/test_db.py`: `mapping_check(conn, day)` — `ref`에 없는 (지역, 사업장)만 반환, `ops.unmapped_name`에 이미 있으면 다시 반환하지 않음, 관측 없는 화면 굴뚝(B) 기록, 새 굴뚝은 기록만.
- [ ] T033 [US2] `db.py`에 요약 SQL(`INSERT … ON CONFLICT DO UPDATE`), `summary_days`, `mapping_check` 구현. `lambda_handler.py`에 `mode=daily`(S3 읽지 않음) (FR-007~010).
- [ ] T034 [US2] `state_machine.tf`: Scheduler `cron(20 3 * * ? *)` 입력 `{"mode":"daily"}`, Notify 단계(`new_names` 있을 때 SNS, 제목 ASCII) (contracts §2).

## Phase 6: US4 - 다시 채우기 (P2)

- [ ] T035 [P] [US4] `tests/test_load.py`: `day_range(date)` — 008 `ktms_pipeline.ingest_dates`·`in_range`와 같은 범위, 미래 날짜 거부.
- [ ] T036 [US4] `lambda_handler.py`에 `mode=day`(그 날짜 원본 → `in_range` → UPSERT `load_path=backfill` → 그 날짜 요약) 구현 (FR-015·016).
- [ ] T037 [US4] `run_dashboard_load.py backfill --from --to [--dry-run]`: 날짜마다 상태 머신 실행(`StartExecution` → 완료 대기), 날짜별 행 수 표 출력, 실패 날짜 목록과 재실행 명령. `status` 명령(`ops.load_run` 10건, 날짜별 행 수).

## Phase 7: US5 - D 앱 공간과 계정 (P3)

- [ ] T038 [P] [US5] `tests/test_db.py`: `tms_app`으로 `obs`·`ref` 쓰기 거부, `app` 쓰기 성공, `rag`에서 `vector` 사용 가능(SC-008).
- [ ] T039 [US5] D 앱 서버 역할(`tms-app` 스택)에 `rds-db:connect` `dbuser:*/tms_app` 추가 여부를 D와 정한다(접속 방식 안내만, 이 기능에서 앱 코드는 쓰지 않음). 📨

## Phase 8: 배포와 운영 확인 (사람)

- [ ] T040 🧑 `build_layer.sh` 실행 후 quickstart §2: `tms-network`(추가만) → `tms-database`(RDS **수정**이지 교체 아님 확인, IAM 인증) → `tms-dashboard-load`(스케줄 꺼짐) plan·apply.
- [ ] T041 🧑 quickstart §3: 베스천 터널 → `migrate` → `load-ref`.
- [ ] T042 🧑 quickstart §4: `recent` 1회 실행, 두 번째 실행 `upserted = 0`(SC-002), 상태 행 null 0건(SC-005).
- [ ] T043 🧑 quickstart §5: `backfill --from 2026-10-30 --to <오늘>`, 1시간 안(SC-006).
- [ ] T044 🧑 quickstart §6: 확정 날짜 2개를 Athena Silver와 비교(SC-003). 다르면 그 날짜 `backfill`.
- [ ] T045 🧑 quickstart §7: `load_schedule_enabled = true` 적용, 다음 :15·:45와 다음 날 03:20 `daily` 확인, 새 슬롯이 40분 안에 보이는지(SC-001).
- [ ] T046 🧑 quickstart §8: RDS 끄고 다음 실행이 `skipped`로 성공·메일 없음 확인 → 다시 켜고 `backfill`로 복구.
- [ ] T047 🧑 quickstart §9: `tms_app` 권한 확인(SC-008), 한 굴뚝 하루 시계열 조회 1초 안(SC-009).

## Phase 9: Polish

- [ ] T048 [P] `AGENTS.md`: 저장소 구조에 `infra/stacks/tms-dashboard-load/`, `services/dashboard-load/`, S3 경로 규칙에 `ref/sites/`(사업장 목록, 사람이 올림, 덮어쓰지 않음), RDS 서비스 복사본 원칙(정본은 S3).
- [ ] T049 [P] D 공유: 테이블·키·상태 번호 약속(data-model), 읽기 예시 SQL, `tms_app` 접속 방식, `ref.status_code.explanation_ko`는 C·B 확인 뒤 채움.
- [ ] T050 spec Status 갱신(운영 시작일, 확인한 SC), 이슈 #62 할 일 체크.

## Dependencies & Execution Order

- Phase 1 → Phase 2(DB 구조·접속) → US1(MVP). US1 안에서 T021·T022(다른 스택)는 T023보다 먼저 apply한다.
- US3(T027~T029)는 Phase 2 뒤 언제든. D의 사업장 목록(📨 T027)을 기다린다. US1은 기다리지 않는다(연결 안 된 관측도 저장됨).
- US2는 US1 뒤(관측이 있어야 요약). US4는 US1 코드 재사용. US5는 Phase 2 뒤 언제든.
- Phase 8은 코드가 머지되거나 브랜치에서 apply할 때 사람이 진행한다.

## Parallel Example: US1

```
T014, T015, T017, T020 (테스트, 서로 다른 파일)  →  T016 load.py · T018 db.py  →  T019 handler
T021 tms-network · T022 tms-database · T025 variables  (서로 다른 스택·파일)
```

## Implementation Strategy

- **MVP = Phase 1~3(US1)**: 30분 적재만으로 지도·시계열이 오늘 값까지 나온다. 연결(US3) 전에도 관측은 쌓인다.
- 다음 US3(지도 연결) → US2(요약·점검, 에이전트 기간 질문) → US4(다시 채우기, 처음 채우기에 필요하므로 배포 전 완료) → US5.
- 처음 배포 순서는 quickstart §2~§7: 인프라 → migrate → load-ref → recent 1회 → backfill → Silver 비교 → 스케줄 켜기.
