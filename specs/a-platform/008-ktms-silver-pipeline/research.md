# Research: K-TMS Silver·ML-ready 매일 갱신 파이프라인

결정 → 이유 → 검토한 대안 순서로 적는다. 규칙 코드는 C의 `src/smokestack_guard/silver/ktms.py`, `ml_ready.py`(PR #45 머지, `7f9c416`)다.

## R1. 실행 환경: Glue 5.0, 계산은 driver의 pandas

- **결정**: Glue 5.0(Spark 3.5.4, Python 3.11, Iceberg 1.7.1 내장)에서 driver가 C의 pandas 함수를 그대로 부르고, Spark는 Iceberg 테이블을 읽고 쓰는 데만 쓴다. 작업자는 G.1X 2대(Glue 최소값)다.
- **이유**:
  - 하루 Silver 약 30만 행, ML-ready 입력(ok인 NOx·SOx)은 그 절반 이하다. pandas로 충분하고, C가 로컬에서 같은 크기로 검증했다.
  - C의 함수를 그대로 부르면 규칙을 다시 짤 일이 없다. 005처럼 Spark로 다시 짜면 규칙이 두 벌이 되고 비교 작업이 생긴다.
  - Iceberg 쓰기(`--datalake-formats iceberg`)가 내장돼 있어 외부 패키지가 필요 없다. 패키지 방식(zip, `--extra-py-files`)도 CEMS와 같다.
- **대안**:
  - Lambda + pyiceberg: 15분 제한과 전체 생성 때의 메모리가 불확실하다. pyiceberg와 pyarrow를 레이어로 묶어야 한다. 기각.
  - Glue Python shell: Iceberg 쓰기가 내장되지 않아 pyiceberg를 패키징해야 한다. 기각.
  - 005처럼 Spark로 규칙을 다시 구현: 이 데이터 크기에서는 얻는 것이 없다. 기각.
- **확인 필요(첫 실행)**: Glue 5.0의 pandas·numpy 버전을 실행 기록에 남긴다. C의 코드는 `pandas>=2.2`만 요구하고, 004·006에서 Glue 5.0의 pandas import가 성공했다.

## R2. 잡 구성: Silver 잡과 ML-ready 잡 2개, 공통 모듈 1개

- **결정**: Glue 잡 `tms-silver2-ktms`(Silver)와 `tms-silver2-ktms-ml-ready`(ML-ready)를 따로 둔다.
  - 공통 코드(날짜 범위 계산, Iceberg 세션, 실행 기록)는 `ktms_pipeline.py` 하나에 두고 두 진입 스크립트가 import한다.
  - Step Functions가 Silver → ML-ready 순서로 부른다.
- **이유**:
  - 단계마다 재시도와 실패 알림이 따로 된다(FR-013).
  - Silver가 성공해야 ML-ready를 돌린다는 조건(FR-012)을 흐름 정의만 보고 알 수 있다.
  - ML-ready만 다시 돌릴 수 있다. 전체 생성(R7)과 C의 ML-ready 규칙 변경 때 필요하다.
  - CEMS(004·005·006)도 Silver 잡과 ML-ready 잡을 나눴다.
- **대안**: 잡 1개가 Silver와 ML-ready를 모두 처리. Glue 시작 시간(약 1분)을 한 번 아끼지만, 단계별 재시도와 ML-ready만 다시 돌리기가 안 된다. 기각.

## R3. Iceberg 테이블 생성: 잡이 `CREATE TABLE IF NOT EXISTS`로 만든다

- **결정**: 테이블 정의(컬럼, 파티션, 속성)는 `ktms_pipeline.py`의 DDL에 둔다. 잡이 실행될 때마다 `CREATE TABLE IF NOT EXISTS`를 실행한다. Terraform은 DB(`tms_silver2`, 이미 있음)와 권한만 다룬다.
- **이유**:
  - Terraform `aws_glue_catalog_table`의 Iceberg 생성 입력으로는 Iceberg 파티션(`days(ts_kst)`)을 지정할 수 없다.
  - Iceberg는 커밋할 때마다 카탈로그의 `metadata_location`을 바꾼다. Terraform이 테이블을 관리하면 매일 상태가 달라진다. `apply`를 하면 그 값을 옛 값으로 되돌려 테이블이 과거 상태로 보일 수 있다. `ignore_changes`로 피할 수는 있지만 파티션 문제는 남는다.
  - DDL은 코드에 있으므로 리뷰와 재현이 가능하다(원칙 III의 취지). 원칙 위반 여부는 plan의 Complexity Tracking에 적었다.
- **대안**:
  - Terraform + `ignore_changes`: 파티션이 없는 테이블이 된다. 기각.
  - Athena DDL을 사람이 한 번 실행: 수동 단계가 남고 코드와 어긋날 수 있다. 기각.

## R4. 테이블 형식과 파티션

- **결정**: Iceberg 형식 버전 2. Silver는 `days(ts_kst)`, ML-ready는 `days(measured_at)`로 파티션한다.
  - 시각 컬럼은 Iceberg `timestamp`(시간대 없음, Spark `TIMESTAMP_NTZ`)다. 값은 KST 벽시계 그대로라서 `days(...)`가 곧 KST 측정일이다.
  - 속성:
    - `write.distribution-mode=hash`: 날짜 하나당 파일 1개 안팎
    - `write.parquet.compression-codec=zstd`
- **이유**:
  - 일 단위로 다시 쓰므로 교체 단위와 파티션을 맞춘다. 숨은 파티션이라 읽는 쪽은 파티션 컬럼을 몰라도 된다.
  - 프로젝트 기간(11월 ~ 12월 중순)에 파티션은 50개 안팎이다.
  - 형식 버전 2는 Athena(엔진 3)와 Glue 5.0이 모두 지원하는 기본값이다.
  - 시간대 없는 타입이라 Spark 세션 시간대가 달라도 값이 바뀌지 않는다. tw_cems도 벽시계 값을 쓴다.
- **대안**:
  - `months(...)`: 하루를 다시 쓸 때도 한 달치 파일을 다시 써야 한다. 기각.
  - `timestamptz`: 읽는 쪽마다 변환이 생긴다. 기각.

## R5. 덮어쓰기: 대상 범위 조건으로 한 번에 교체

- **결정**: `writeTo(table).overwrite(<시각 컬럼> >= 시작일 00:00 AND < 끝 다음날 00:00)`로 대상 날짜만 교체한다.
  - 테이블마다 실행당 커밋 1번이다.
  - 쓰기 전에 결과를 대상 범위로 걸러, 범위 밖 행은 쓰지 않는다.
  - 스냅샷 요약에 `job_run_id`, `range`를 남긴다(`snapshot-property.*`).
- **이유**:
  - 조건이 날짜 파티션 경계와 맞아서 파일을 다시 쓰지 않고 파일 단위로 교체된다.
  - 커밋은 원자적이라 진행 중에는 직전 버전이 보인다(FR-009, US3-3).
  - 동적 파티션 덮어쓰기(`overwritePartitions`)는 결과가 0행인 날짜를 비우지 않는다. 범위 조건이 의도를 더 정확히 나타낸다.
- **0행 처리(FR-010)**:
  - 전체 결과가 0행이면 쓰기 전에 실패한다.
  - 대상 날짜 중 일부만 0행이면 쓰고, 실행 기록의 `empty_days`에 남긴다. 원본은 추가만 되므로, 다시 계산해서 기존보다 행이 줄 일은 없다.
- **동시 쓰기(FR-015)**: 잡마다 `max_concurrent_runs = 1`로 둔다. 겹친 실행은 `ConcurrentRunsExceededException`이 나고, Step Functions가 기다렸다 다시 시도한다(R8). 그래도 겹쳐 쓰면 Iceberg의 커밋 충돌 검사가 나중 커밋을 실패시킨다.

## R6. 읽는 범위

### Silver

- **처리 범위**: KST 측정일 `[start, end]`. 기본값은 C의 `last_complete_day()`를 `end`로, `start = end − 1`로 둔다.
- **원본 범위**: UTC 수집일 `[start − 1, min(end + 1, 오늘 UTC)]`을 `read_bronze(bucket, start, end)`에 넘긴다.
  - KST D 00:00은 UTC D−1 15:00이다.
  - 수집일 `end + 1`(UTC)까지 읽으면 KST `end + 2`일 09:00까지 들어온 지연·정정이 반영된다. 실측 최대 지연은 약 3시간이다.
  - 매일 실행에서는 `end + 1`이 오늘(UTC)과 같아서 실행 시각까지 읽는 것과 같다.
- **처리 순서**: `to_silver` 결과를 `ts_kst`의 KST 날짜가 `[start, end]`인 행으로 거른다. 진행 중인 오늘은 `end`를 넘으므로 쓰지 않는다.
- **한 번에 처리할 날짜 수**: 최대 7일(`--max_days`, 기본 7)로 둔다. 원본 3일치를 pandas로 펼치면 수백만 행이고, 전체 생성(약 15일)을 한 번에 하면 driver 메모리(16GB)가 부족할 수 있다. 실제 메모리 사용량은 첫 실행 로그로 확인한다.

### ML-ready

- **입력**: Silver 테이블에서 `[start 00:00 − 150분, end + 1일 00:00 + 30분]`(양 끝 포함, 즉 첫 칸 00:00의 150분 전부터 마지막 칸 23:30의 60분 뒤까지)을 읽어 `to_ml_ready`에 넣는다. 결과는 `measured_at`이 `[start, end]`인 행만 남긴다.
- **이유**: `to_ml_ready`가 대상 행에서 보는 범위가 앞 150분 ~ 뒤 60분이기 때문이다.
  - 앞 150분: lag 150, rolling 6칸, rise_count, 기준치 변경 창
  - 뒤 60분: 라벨 `shift(−1, −2)`, 기준치 변경 창의 `shift(−2)`
  - 그룹마다 첫 관측부터 마지막 관측까지 30분 격자로 펼치므로, 앞뒤 칸을 더 넣어도 대상 행의 값은 전체 기간으로 계산한 값과 같다. 이것을 단위 테스트로 확인한다(테스트 T-ML-1).
- **매일 실행에서 생기는 일**: `end + 1`일(오늘)은 아직 Silver에 없으므로 `end`일 마지막 1시간의 라벨은 비어 있다. 다음 날 실행이 그날을 다시 계산하면서 채운다(spec US1-3).

## R7. 처음 전체 생성(US2): Silver는 나눠서, ML-ready는 한 번에

- **결정**: 사람이 실행하는 `run_ktms.py backfill --from 2026-10-30 --to <어제>`가 다음 순서로 Step Functions를 실행한다.
  1. `stage=silver`로 날짜를 묶음(기본 5일)씩 차례로 처리한다.
  2. 마지막에 `stage=ml_ready`로 전체 범위를 한 번에 처리한다.
- **이유**:
  - Silver는 날짜마다 독립이라 나눠도 결과가 같다.
  - ML-ready를 묶음별로 하면 묶음 경계의 라벨이 다음 묶음 Silver 없이 계산돼 비게 된다. Silver를 다 만든 뒤 한 번에 하면 경계 문제가 없다.
  - ML-ready 입력은 15일 기준 약 150만 행이라 driver 하나로 충분하다. C가 같은 범위를 로컬에서 처리했다.
- **대안**: Silver 잡을 G.2X로 한 번에. 메모리 추정이 불확실하고 비용이 2배다. 첫 시도가 실패하면 그때 검토한다.

## R8. 흐름: EventBridge Scheduler → Step Functions(Standard) → Glue

- **Scheduler**: `cron(0 3 * * ? *)`, 시간대 `Asia/Seoul`, 유연한 시간 창 OFF, 입력 `{}`. 수집 스케줄 규칙(AGENTS.md)과 같은 형식이다.
- **상태 머신** `tms-silver2-ktms`:
  1. `Defaults`(Pass): 입력에 기본값(`start_date="auto"`, `end_date="auto"`, `stage="all"`)을 합친다.
  2. `Choice`: `stage`가 `ml_ready`이면 3을 건너뛴다.
  3. `Silver`: `glue:startJobRun.sync`
  4. `Choice`: `stage`가 `silver`이면 끝낸다.
  5. `MlReady`: `glue:startJobRun.sync`
- **재시도**:
  - `Glue.ConcurrentRunsExceededException`: 120초 간격 × 5회. 겹친 실행을 기다린다.
  - 그 밖의 오류(`States.ALL`): 60초 뒤 1회(FR-013).
- **실패 처리**: `Catch`가 `sns:publish`(토픽 `tms-collector-alerts`, 제목 `[tms] K-TMS silver2 실패`, 본문은 실행 이름·단계·오류 요약)를 보낸 뒤 `Fail`로 끝낸다.
  - SC-006(10분 안 알림): Glue 실패까지 수 분, 재시도 간격 60초 뒤 바로 게시되므로 맞출 수 있다.
- **Standard를 쓰는 이유**: `.sync` 통합과 실행 이력(90일)을 쓰려고 한다. 하루 1회라 상태 전환 비용은 무시할 만하다.
- **대안**:
  - Scheduler가 Glue를 직접 실행: 두 단계의 순서와 재시도를 표현할 수 없다. 기각.
  - Glue Workflow: 알림과 입력 기본값 처리가 번거롭다. 기각.

## R9. 합성 입구(US5): 인자만 두고 리소스는 나중에

- **결정**:
  - 진입 스크립트에 `--source_prefix`(기본 `tms_cleansys/`), `--silver_table`, `--ml_ready_table` 인자를 둔다.
  - `--source_prefix`가 기본값이 아닌데 C의 `read_bronze`에 경로 인자가 없으면, 읽기 전에 "C의 read_bronze 경로 인자 필요"로 실패한다. 인자 존재는 `inspect.signature`로 확인한다.
  - 합성용 Glue 잡, 테이블, 권한은 이번에 만들지 않는다.
- **이유**:
  - C의 `ktms.PREFIX`가 `tms_cleansys/`로 고정돼 있다. 우회해 읽지 않기로 결정했다(2026-11-13).
  - B의 경로(`episode=` 단계)와 생성 방식이 아직 바뀔 수 있다.
  - 읽지 못하는 테이블과 권한을 미리 만들 이유가 없다.
- **나중에 할 것**: C가 경로 인자를 추가하고 B가 실제로 합성 데이터를 올리면 다음을 추가한다.
  - 합성 전용 잡 2개: 같은 스크립트를 쓰고 기본 인자만 다르다. 실측 잡과 동시 실행 한도를 나누려는 것이다(FR-019).
  - 상태 머신 하나
  - 권한: `tms_synthetic/*` 읽기, `silver2/ktms_synthetic*` 쓰기

## R10. 실행 기록과 버전

- **위치**: `silver2/_runs/ktms/<시작 UTC>_<job_run_id>.json`, `silver2/_runs/ktms_ml_ready/…`. 실행마다 파일 하나이며, 성공하거나 실패한 시도마다 남긴다.
- **내용**:
  - 공통: `result`(`succeeded`/`failed`), `error`, 범위, 원본 수집일 범위, 읽은 스냅샷 수
  - Silver: C의 `quality()` 결과(행 수, `status`별 건수, 중복 키, 날짜별 행 수), `empty_days`
  - ML-ready: 학습 가능 행 수, 양성 행 수
  - 버전: Iceberg `snapshot_id`, `package_md5`(C 코드 zip의 MD5, Terraform이 기본 인자로 넘김), pandas·numpy·Spark 버전, Step Functions 실행 이름
- **이유**: 테이블 버전(`snapshot_id`)과 규칙 코드 버전을 함께 남겨야 "어떤 규칙으로 만든 어느 버전인지"를 따라갈 수 있다(원칙 VI, FR-016). 실패 기록은 `try/except`에서 쓰고 예외를 다시 던진다(FR-017).

## R11. 테스트

- **단위 테스트**(Spark 없이, `tests/test_ktms_pipeline.py`):
  - 처리 범위·원본 범위 계산(자정 경계, `auto`, 7일 초과 거부)
  - ML-ready 앞뒤 범위 동등성(T-ML-1): 같은 가짜 Silver로 전체 `to_ml_ready` 결과와 "앞뒤 범위만 넣고 대상 행만 남긴" 결과가 35컬럼 모두 같은지
  - 합성 경로 거부(R9), 실행 기록 형식
- **Iceberg 통합 테스트**(`tests/test_ktms_iceberg.py`, 표시 `iceberg`):
  - 로컬 Spark 3.5.4와 `iceberg-spark-runtime-3.5_2.12:1.7.1`(`spark.jars.packages`)로 임시 폴더에 Hadoop 카탈로그를 만든다.
  - 확인할 것: 범위 교체 시 다른 날짜가 그대로인지, 같은 입력으로 두 번 실행한 결과가 같은지(SC-004), 이전 `snapshot_id`로 읽은 결과가 그대로인지(SC-005), 0행이면 커밋하지 않는지
  - CI에서 같이 돈다. Maven에서 jar를 받는다.
- **실제 데이터 비교(SC-001·002)**: quickstart에서 사람이 Athena 집계를 PR #45 수치와 비교한다.
- **C 코드가 바뀔 때**: `.github/workflows/tms-silver.yml`이 `src/smokestack_guard/silver/**` 변경에도 돌아서, 함수 이름·인자 변경이 머지 전에 잡힌다.

## R12. 비용

| 항목 | 추정 |
|---|---|
| Glue | 매일 2잡 × 2 DPU × 약 4분 = 하루 약 0.27 DPU-시간. 저장소 `run_silver.py`의 단가($0.308/DPU-시간)로 **월 약 $2.5**, 단가가 $0.44여도 월 약 $3.5다. 첫 실행 기록으로 다시 계산한다 |
| Step Functions(Standard) | 하루 약 10번 상태 전환. 무료 한도 안 |
| EventBridge Scheduler | 월 30번 호출. 무료 한도 안 |
| S3 | 매일 GET 수백 건과 PUT 수십 건, 매일 다시 쓰는 2일치(수십 MB) 누적. 오래된 Iceberg 버전을 정리하지 않으면 월 1GB 안팎씩 늘어 월 $0.03 수준 |
| 전체 생성(1회) | Silver 3묶음과 ML-ready 1번 → 약 $0.3 |

## R13. AGENTS.md 예외 (FR-021)

이 PR에서 AGENTS.md "S3 경로 규칙"에 다음을 추가한다.

> Iceberg 테이블(`tms_silver2.ktms`, `tms_silver2.ktms_ml_ready`)은 예외다. 파티션은 테이블 형식의 숨은 날짜 파티션이고 폴더 이름(`year=/month=`)으로 나타나지 않는다. Spark·pandas·Athena 모두 S3 경로가 아니라 카탈로그로 읽는다(`specs/a-platform/008-ktms-silver-pipeline/contracts/ktms-tables.md`).

저장소 구조 표의 `tms-silver/` 설명에 K-TMS를 추가한다. 테이블 형식과 파티션은 C의 리뷰를 받는다(원칙 IV).
