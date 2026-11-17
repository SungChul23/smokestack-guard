# Research: K-TMS ML-ready 계약 검사 단계

## R1. 실행 단위: Lambda

- **결정**: Lambda 1개(Python 3.12, 메모리 2048MB, 제한 시간 300초, 재시도는 상태 머신이 1회).
- **이유**: 하루 범위 2일 + 여유 구간은 수만 행이라 pandas 한 번으로 충분하다. Glue는 시작만 1분 이상 걸리고 최소 2워커 과금이다.
- **대안**: Glue Python Shell(시작 느림, 이 규모에 과함), Glue Spark(같은 이유), ML-ready 잡 안에서 검사(잡이 실패와 위반을 구분하지 못하고 검사만 따로 돌릴 수 없음).

## R2. 의존성: 관리형 레이어 + 기존 규칙 zip

- **결정**: 레이어 2개. ① AWS SDK for pandas 관리형 레이어(`AWSSDKPandas-Python312`, ARN은 변수 `pandas_layer_arn`) ② 기존 `data.archive_file.package`(Glue가 쓰는 `smokestack_guard.zip`)를 그대로 레이어로. 이 zip은 루트에 `smokestack_guard/`가 있어 `/opt/smokestack_guard`에 풀리므로 진입점이 `sys.path`에 `/opt`를 넣는다.
- **이유**: 판정 코드가 Glue와 같은 한 벌이다. 패키지를 따로 빌드하지 않는다.
- **확인 필요**: 관리형 레이어 버전 번호. apply 전에 `aws lambda get-layer-version-by-arn --arn <ARN>`으로 있는지 본다(사용자 실행).

## R3. 범위와 스냅샷: ML-ready 실행 기록에서 읽는다

- **결정**: 정상 흐름에서는 상태 머신이 넘긴 ML-ready `JobRunId`로 `silver2/_runs/ktms_ml_ready/*_<JobRunId>.json`을 찾아 `range`와 `snapshot_id`를 쓴다. `stage=check`일 때는 입력 날짜(또는 `auto` → `resolve_range`)와 테이블 최신 스냅샷을 쓴다.
- **이유**: "auto"를 Lambda가 다시 해석하면 자정 근처 수동 실행에서 범위가 어긋날 수 있다(FR-003). 기록된 `snapshot_id`로 읽으면 검사 중 다른 갱신이 끼어도 같은 데이터를 본다.
- **대안**: 상태 머신 입력의 날짜만 사용(auto면 불일치 위험), Glue 출력 전달(`startJobRun.sync` 결과에 잡 출력이 없음).

## R4. 읽기: Athena 시간 여행

- **결정**: `SELECT * FROM tms_silver2.ktms_ml_ready FOR VERSION AS OF <snapshot_id> WHERE measured_at BETWEEN lo AND hi`를 awswrangler(`ctas_approach=False`)로 읽는다. 창 `lo, hi`는 `ktms_pipeline.ml_ready_window(range)`(앞 150분, 다음날 00:30)로 ML-ready 잡과 같게 한다. 워크그룹은 기존 `tms-eda`(결과는 EDA 버킷 `athena-results/`, 스캔 한도 있음).
- **이유**: Lambda에는 Spark가 없다. Athena는 Iceberg 시간 여행을 지원한다. 2일치는 수 MB라 비용이 거의 없다.
- **대안**: pyiceberg(레이어에 없음, 패키지 추가 필요), S3 Parquet 직접 읽기(Iceberg 삭제 파일·스냅샷을 무시하게 됨).

## R5. 판정: C의 규칙 + 범위 한정 재계산

- **결정**:
  - 형식·규칙 검사: `ml_ready_check._format_checks(대상 행, expected_source)`, `_rule_checks(대상 행)`을 그대로 부른다.
  - 재계산: 창 전체의 원본 열(`SOURCE_COLUMNS`)로 `to_ml_ready`를 돌리고, **대상 범위 행만** 테이블과 비교한다. 비교 규칙(건너뛸 열 `SKIP_RECOMPUTE`, 키 `KEY`, 허용 오차 1e-4, NaN 같음, bool·object 비교)은 `ml_ready_check._recompute_checks`와 똑같이 하고, 상수는 그 모듈에서 import한다.
  - 굴뚝 키 겹침(합성용)은 `check()`와 같은 문구로 만든다.
- **이유**: `check()`는 받은 행 전체를 재계산·비교해서, 범위만 넘기면 가장자리 오탐이, 창을 넘기면 창 끝 오탐이 난다. 판정 규칙은 그대로 두고 "어느 행을 비교하나"만 바꾼다.
- **후속**: C에게 `check(df, …, compare_from=, compare_to=)` 같은 범위 인자를 제안한다. 들어오면 이 부분을 그 호출로 바꾼다. 비교 규칙이 C 코드와 어긋나지 않도록 같은 표본으로 두 결과를 맞추는 테스트를 둔다.
- **라벨 빈 값(FR-005)**: 매일 실행 직후 마지막 날 끝 1시간은 테이블에도 다음날 행이 없어 재계산 결과도 비므로 별도 예외 없이 일치한다. 테스트로 확인한다.

## R6. 권한 (최소)

| 역할 | 권한 | 범위 | 이유 |
|---|---|---|---|
| 검사 Lambda | `s3:GetObject`, `s3:ListBucket` | 원본 버킷 `silver2/ktms_ml_ready/*`, `silver2/_runs/ktms_ml_ready/*` | 테이블 데이터·메타데이터, ML-ready 실행 기록 |
| 〃 | `s3:PutObject` | `silver2/_runs/ktms_ml_ready_check/*` | 자기 실행 기록만(FR-012) |
| 〃 | `athena:StartQueryExecution`, `GetQueryExecution`, `GetQueryResults`, `StopQueryExecution` | 워크그룹 `tms-eda` | 조회 |
| 〃 | `glue:GetDatabase`, `GetTable`, `GetPartitions` | `tms_silver2` DB와 `ktms_ml_ready` | Athena가 카탈로그를 읽음 |
| 〃 | `s3:GetObject`, `PutObject`, `ListBucket`, `GetBucketLocation` | EDA 버킷 `athena-results/*` | Athena 결과 |
| 〃 | 로그 쓰기 | 자기 로그 그룹 | |
| 상태 머신(기존 역할에 추가) | `lambda:InvokeFunction` | 검사 Lambda | 단계 실행 |

- 테이블 쓰기(`silver2/ktms_ml_ready/*` Put/Delete), Glue 카탈로그 수정, SNS 발행 권한은 Lambda에 주지 않는다. 알림은 상태 머신이 보낸다(기존 `PublishAlert`).

## R7. 알림 구분과 문안

- **결정**: Lambda가 `result`와 함께 `subject`, `message`를 만들어 돌려주고, 상태 머신이 그대로 발행한다. 실행 자체 실패는 상태 머신 Catch가 별도 문안으로 보낸다.

| 경우 | 제목 |
|---|---|
| 위반 | `[tms] K-TMS contract violation - ktms_ml_ready <start>~<end> (<건수>)` |
| 검사할 행 없음 | `[tms] K-TMS contract check: no rows - ktms_ml_ready <start>~<end>` |
| 검사 실행 실패 | `[tms] K-TMS contract check failed` |
| (기존) 갱신 잡 실패 | `[tms] K-TMS silver2 failed` |

- 제목은 SNS 제약(ASCII만)으로 영어, 본문은 한국어. 본문은 contracts/check-interface.md §4. 위반 항목은 최대 10건 + "외 N건".
- **이유**: 상태 머신 `States.Format`으로 목록을 만들 수 없다. 문안을 코드에서 만들면 단위 테스트로 형식을 고정할 수 있다.

## R8. 모드와 시험 입력

- **결정**:
  - Terraform 변수 `ktms_check_mode` = `observe`(기본) | `block`. 상태 머신 정의에 들어간다. `observe`: 위반·행 없음·검사 실패 모두 알림만, 실행은 성공. `block`: 위반과 검사 실패면 알림 뒤 실행 실패.
  - 실행 입력: `stage` = `all`(기본) | `silver` | `ml_ready` | `check`, `notify` = `true`(기본) | `false`, `check_table`(기본 `tms_silver2.ktms_ml_ready`), `expect_source`(기본 없음), `real_table`(기본 없음).
  - `stage=check`: Glue 잡 없이 검사만. 날짜는 입력값(기본 auto).
- **이유**: 매일 스케줄이 이미 켜져 있어 첫 배포 순간부터 운영 실행에 들어간다. 관찰 모드면 검사 쪽 문제로 파이프라인이 실패하지 않는다.

## R9. CI

- **결정**: `tms-silver.yml`에 "루트 규칙 테스트" 단계를 추가해 저장소 루트에서 `PYTHONPATH=src pytest -q tests`를 돈다. 트리거 경로에 `tests/**`를 더한다. 새 Lambda 테스트는 `services/tms-silver/tests`에 두어 기존 단계가 돈다.
- **이유**: #52·#56의 테스트가 지금 어떤 워크플로에서도 돌지 않는다.
