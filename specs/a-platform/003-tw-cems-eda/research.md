# Research: TW CEMS Athena EDA 환경

**Date**: 2026-11-04 · **Spec**: [spec.md](spec.md) · **Plan**: [plan.md](plan.md)

2026-11-04에 AWS를 읽기 전용으로 조회하고, PyPI와 AWS Pricing API를 확인한 결과다.

## R1. Glue 버전과 provider 지원

- **Decision**: `glue_version = "6.0"`, `command.python_version = "3"`, 실행 클래스 `STANDARD`.
- **Rationale**:
  - 계정에 콘솔로 만든 테스트 Job `cems-eda전용`이 이미 `GlueVersion 6.0`으로 존재한다. 리전에서 쓸 수 있는 버전이다.
  - provider는 `hashicorp/aws 6.71.0`(`tms-collection` 잠금 파일)이다. `glue_version`은 문자열 그대로 전달되므로, `terraform validate`와 `plan`으로 최종 확인한다.
  - 로컬 Spark 버전은 지시서(AWS 문서 기준)의 Spark 4.1.1에 맞춘다. Job이 시작할 때 `spark.version`을 로그에 남겨 실제 버전을 확인한다.
- **Alternatives considered**:
  - **Flex 실행 클래스**: 6.0+ 기준 DPU-시간당 $0.203, 약 34% 저렴하다. 1회성이라 적합하지만, 시작 지연이 예측되지 않아 30분 timeout과 충돌할 수 있다. 총비용 차이가 몇 달러라서 STANDARD로 둔다. map 항목의 값 하나라 나중에 바꾸기 쉽다.

## R2. 비용 단가 (AWS Pricing API, ap-northeast-2)

| 항목 | 단가 |
|---|---|
| ETL Job, Glue 6.0+ (`APN2-ETL-DPU-Hour-Gen2`) | $0.308 / DPU-시간 |
| ETL Flex, Glue 6.0+ | $0.203 / DPU-시간 |
| 크롤러 | $0.44 / DPU-시간 (최소 10분) |
| Athena | $5 / 스캔 TB |

- **Decision**: 백필 스크립트의 비용 추정에 $0.308을 쓴다.
- **추정 방법**: `get_job_run`의 `DPUSeconds`를 쓴다. 이 값은 Auto Scaling이나 Flex일 때만 채워지는 필드라서, 비어 있으면 `ExecutionTime × NumberOfWorkers × 1 DPU`(G.1X = 1 DPU)로 계산한다.

## R3. 읽기 방식: 스키마 추론, 문자열 보존, 손상 줄

- **Decision**: 아래 옵션으로 읽는다.
  ```
  spark.read
    .option("primitivesAsString", "true")
    .option("mode", "PERMISSIVE")
    .option("columnNameOfCorruptRecord", "_corrupt_record")
    .json(<월 파일 1개>)
  ```
  - 스키마를 주지 않고, `samplingRatio`는 기본값 1.0(전체)을 쓴다.
- **Rationale**:
  - 다른 달의 키를 모르므로 추론해야 한다(FR-002).
  - 표본 추론을 쓰면 드물게 나오는 키(플레어 행)를 놓칠 수 있다.
  - `primitivesAsString`은 숫자·불리언을 원문 문자열로 둔다(FR-003).
  - PERMISSIVE는 손상된 줄을 `_corrupt_record`에 원문으로 남긴다(FR-004).
- **비용**: 스키마 추론에 월 파일을 한 번 더 읽는다. 고정 스키마를 쓰지 않는 대가이며, R7 추정에 포함했다.
- **주의**:
  - `multiLine`은 쓰지 않는다. 쓰면 파일이 나뉘지 않는다.
  - 최상위가 배열인 줄은 Spark가 여러 행으로 펼친다. 이 경우 행 수가 달라지고, R5 검증에서 실패로 잡힌다.
- **Alternatives considered**:
  - 고정 스키마: 모르는 키가 조용히 버려진다. 기각.
  - `DROPMALFORMED`: 행 수가 달라진다. 기각.

## R4. 출력 파일 수: `coalesce` 대신 `repartition`

- **Decision**: `df.repartition(2).write.mode("overwrite").parquet(...)`를 쓴다.
- **Rationale**:
  - `coalesce(2)`는 셔플 없이 상위 단계까지 병렬도를 2로 줄인다. 그러면 2.5GB JSON 파싱을 태스크 2개가 하게 된다(Spark 실행 계획 특성).
  - `repartition(2)`는 읽기·파싱을 전체 병렬로 하고, 마지막에만 2개로 모은다. 셔플 양은 Parquet 직전 행 데이터 수준이다.
  - 월당 출력이 약 100~300MB(추정)라서 2개 파일이면 Athena 읽기에 알맞다.
- **Alternatives considered**: 지시서의 `coalesce(2)`. 위 이유로 바꾼다. Complexity Tracking에 기록했다.
- **(2026-11-05 실측)** 2025-03(2.78GB)이 10 DPU로 83초, 출력 72.7MB × 2개였다.
  - Glue 6.0에서는 `_SUCCESS`가 생기지 않았다(로컬 Spark는 생김). Glue가 기본으로 완료 표지를 끈다.
  - 쓰기 옵션 `mapreduce.fileoutputcommitter.marksuccessfuljobs=true`로 명시적으로 켠다.

## R5. 행 수 확인과 완료 표지

- **Decision (2026-11-04 사용자 결정, B안)**:
  - Job 안에서 행 수를 검증하지 않는다.
  - 완료 표지는 Spark가 쓰기를 마칠 때 남기는 기본 `_SUCCESS`(빈 파일)를 그대로 쓴다.
  - SC-002(행 수 = 줄 수)는 표본 1~2개월만 사람이 확인한다. 방법: 원본을 스트리밍해 비어 있지 않은 줄을 세고(`aws s3 cp … - | grep -c .`), Athena 월별 `count(*)`와 비교한다.
- **Rationale**:
  - PERMISSIVE 모드는 손상 줄도 한 행으로 남기므로 행 수는 원래 맞게 나온다. 자동 검증은 보험에 가깝다.
  - EDA 목적에 비해 원본을 한 번 더 읽는 비용과 코드 증가가 이득보다 크다.
- **남는 위험**:
  - 최상위가 배열인 줄은 여러 행으로 펼쳐질 수 있다.
  - 이런 경우는 표본 확인과 EDA 중에 발견한다. 발견되면 그 월을 다시 판단한다.
- **표지 처리**:
  - Athena는 `_`로 시작하는 파일을 무시한다.
  - 크롤러에는 `**/_SUCCESS`를 제외 패턴으로 준다.
  - `--only-missing`은 이 표지가 있는지만 본다. 쓰기가 끝까지 성공했다는 뜻이며, 행 수 검증은 아니다.
- **Alternatives considered**:
  - A안(Job이 원본 줄 수를 다시 세서 비교한 뒤 자체 표지를 씀): 24개월 전체가 자동 확인되지만, 텍스트 읽기 한 번(총 +$1~2)과 코드가 늘어난다. 사용자 결정으로 기각.

## R6. 대소문자만 다른 키

- **Decision**: 추론된 컬럼 이름을 소문자로 바꿨을 때 중복이 있으면 Job을 실패시킨다(Edge Case).
- **Rationale**:
  - Glue 카탈로그와 Athena는 컬럼 이름을 소문자로 다룬다. `ImportDate`와 `importdate`가 같이 있으면 테이블에서 충돌한다.
  - Spark 쪽 동작(`spark.sql.caseSensitive=false`)에 맡기지 않고 명시적으로 검사한다. 오류 메시지에 충돌한 이름을 적는다.
  - (구현 중 확인) 기본 설정에서는 Spark가 스키마 추론 단계에서 `COLUMN_ALREADY_EXISTS`로 먼저 실패하고, 메시지에 소문자 이름 하나만 나온다. 그래서 읽는 동안만 `caseSensitive=true`로 두고 읽은 뒤 원래 값으로 되돌린다.

## R7. 처리 시간과 비용 추정

- **가정**:
  - 월 2.4GB, G.1X 10개(실행자 9개 × 4 vCPU = 36코어)
  - (2026-11-05 변경) 처음엔 5개·동시 2~3개였으나, 백필을 빨리 끝내려고 10개·동시 6개로 올렸다. 계정 동시 DPU 한도 500 안이다. 이전 테스트에서 1.5GB를 10 DPU로 약 1분에 변환했다. 비용은 DPU × 시간이라 거의 같고(약 $1 증가), 쓰기 단계(파일 2개)에서 남는 코어만큼 손해가 있다.
  - 읽기 두 번: 스키마 추론, 파싱·쓰기
  - 시작 약 1분
- **추정**: 월당 약 3분(시작 1분 포함), 약 0.5 DPU-시간, 약 $0.15~0.22.
  - 24개월: **약 $4~6**, 동시 6개로 약 15분
  - 재시도와 재실행을 포함해도 SC-004의 $20 이하
- 크롤러 1회는 약 $0.1~0.2, Athena 한 달 조회는 $0.01 미만(추정)이다.
- 실제 값은 백필 결과 표로 확인한다.

## R8. 로그

- 계정에 `/aws-glue/jobs/output`, `/aws-glue/jobs/error`, `/aws-glue/jobs/logs-v2`, `/aws-glue/crawlers`가 이미 있다. 콘솔 테스트에서 생겼고, 보존 기간은 "만료 없음"이다.
- **Decision**:
  - 연속 로그는 이 스택이 만드는 로그 그룹 `/aws-glue/tms-eda`(보존 14일)로 보낸다(`--continuous-log-logGroup`).
  - 기존 공용 그룹은 다른 리소스와 공유하므로 Terraform으로 가져오거나 바꾸지 않는다.
  - Glue가 공용 `output`/`error` 그룹에 남기는 로그는 그대로 둔다. 1회성이라 양이 적다.
- `AWSGlueServiceRole` 관리형 정책이 `/aws-glue/*` 로그 그룹 쓰기를 허용하므로 추가 권한은 필요 없다.

## R9. 크롤러 설정과 테이블 이름

- **Decision**: 대상은 `s3://smokestack-tms-eda-952900391026/tw_cems_raw/` 하나다.
  - 제외 패턴 `**/_SUCCESS`
  - `recrawl_policy = CRAWL_EVERYTHING`
  - `UPDATE_IN_DATABASE` / `LOG`
  - `CombineCompatibleSchemas`, 파티션은 `InheritFromTable`
  - 스케줄 없음
- **Rationale**:
  - 대상 폴더 바로 아래가 `year=/month=` 파티션이면, 크롤러가 폴더 이름으로 `tw_cems_raw` 테이블 하나를 만든다.
  - 달마다 컬럼이 달라도 `CombineCompatibleSchemas`가 하나로 합친다.
  - 파티션 값의 타입은 문자열(`'2025'`, `'03'`)로 추론된다.
- **위험**: 스키마가 크게 다르면 크롤러가 테이블을 여러 개 만들 수 있다. quickstart에 "테이블이 하나인지 확인"을 넣었다. 여러 개면 원인(키 구성)을 보고 사람이 판단한다.

## R10. EDA 버킷 구성

- **Decision**: 스택 안에서 버킷 리소스를 직접 정의한다.
  - 공개 차단, 소유권 강제, 버전 관리, SSE-S3, `prevent_destroy`
  - 수명 주기:

    | 경로 | 현재 버전 | 이전 버전 |
    |---|---|---|
    | `athena-results/` | 30일 | 1일 |
    | `glue-temp/` | 7일 | 1일 |
    | `tw_cems_raw/` | (만료 없음) | 7일 |
    | 버킷 전체 | 미완료 멀티파트 7일 정리 | |

- **Rationale**:
  - 버전 관리를 켜면 월 단위 덮어쓰기로 지워진 Parquet이 이전 버전으로 계속 남는다. 파생본이므로 이전 버전은 7일 뒤 정리한다.
  - `raw-archive` 모듈은 "원본은 수명 주기를 두지 않는다"는 목적의 모듈이라 재사용하지 않는다.
- **Alternatives considered**:
  - 버전 관리 끄기: 실수로 덮어쓴 것을 7일 안에 되돌릴 수 있는 장점을 버리게 된다. 비용 차이가 작아 켠다.

## R11. 로컬 개발 환경

- PyPI `pyspark` 릴리스에 `4.1.1`이 있다. 요구 Python은 `>=3.11`이고 3.13 분류자가 있다.
- WSL 현재 상태:
  - Python 3.14만 있다. `uv`가 설치되어 있으므로 `uv python install 3.13`으로 맞춘다.
  - **Java가 없다.** PySpark 4는 Java 17 이상이 필요하므로 `openjdk-17-jdk-headless` 설치가 필요하다(사용자 작업, quickstart에 기록).
- **Decision**:
  - `pyproject.toml`: `requires-python = ">=3.13,<3.14"`
  - dev 의존성: `pyspark==4.1.1`, `boto3`, `pytest`, `ruff`
  - CI: Temurin 17 + Python 3.13

## R12. 실행 인자 처리

- **Decision**: `argparse.parse_known_args()`를 쓴다.
  - Glue가 넘기는 `--JOB_NAME`, `--JOB_ID`, `--TempDir` 같은 인자는 무시한다.
  - `awsglue` 라이브러리를 import하지 않아 로컬에서도 같은 스크립트가 돈다.
  - 북마크는 끈다(`job-bookmark-disable`).
- **Alternatives considered**: `awsglue.utils.getResolvedOptions`. 로컬에 `awsglue`가 없어 테스트가 어렵다. 기각.
