# Research: TW CEMS Silver 클라우드 실행 (Glue, 36개월)

plan의 기술 결정과 그 이유를 적는다. 각 항목은 결정 → 이유 → 검토한 대안 순서다.

## R1. 실행 환경: Glue 5.0

- **결정**: Glue 5.0. Spark 3.5.4, Python 3.11, Java 17이다.
- **이유**:
  - C가 로컬에서 검증한 조건(`apache/spark:3.5.4`, Java 17)과 Spark 버전이 같다.
  - 201 spec의 FR-018도 "Spark 3.5 기준(Glue 5.0/5.1)"이다.
- **대안**:
  - Glue 6.0 (`tms-eda`가 쓰는 버전): 기각. Spark 4.1.1, Python 3.13이라 검증 조건과 메이저 버전이 다르다. 체크리스트 6장에 적힌 pandas↔Spark 버전 민감성이 다시 문제가 될 수 있다.
  - Glue 4.0 (Spark 3.3): 기각. 코드는 동작하지만 검증한 3.5보다 오래되었다.
- **pandas는 import만 필요하다**:
  - Glue에서 계산은 모두 Spark가 한다. pandas는 쓰지 않는다.
  - 다만 `tw_cems_spark.py`가 `tw_cems.py`(pandas 구현)에서 상수를 import하고, `tw_cems.py`는 맨 위에서 `pandas`·`numpy`를 import한다. 그래서 pandas가 **설치되어 있어야** 한다.
  - pandas 버전은 Silver 결과에 영향이 없다.
  - Glue 5.0에는 pandas가 기본으로 들어 있다고 예상한다. 첫 실행에서 import가 되는지와 버전을 실행 기록에 남긴다.
  - import가 실패할 때만 `--additional-python-modules pandas`를 Job 인자로 추가한다.
- **pandas 구현의 역할**: Silver에서 `tw_cems.py`는 검증 기준(201 FR-018의 의미 기준선)이고, 상수를 제공한다.
- **후속 제안 (C)**: 상수를 pandas 없는 모듈로 분리하고 `build()`를 변환·쓰기로 나누는 것. 004에서는 C의 코드를 고치지 않는다(2026-11-09 사용자 결정).

## R2. 입력 읽기: C의 `read_raw`를 그대로 쓴다

- **결정**: `tw_cems_spark.read_raw`(스키마 추론, `primitivesAsString=true`)로 읽는다. 읽은 뒤 Silver에 필요한 원본 10개 컬럼만 골라 `persist`한다.
- **이유**:
  - 검증된 읽기 방식과 같다.
  - 일부 달(2023-11~12 재업로드본)은 키 대소문자가 다를 수 있어 C의 `prep`이 컬럼 이름을 소문자로 바꾼다. 고정 스키마로 읽으면 대소문자가 다른 키가 null이 될 위험이 있다.
  - `persist`해 두면 원본을 다시 읽지 않고 입력 행 수(FR-010)를 셀 수 있다. 월당 약 440만 행 × 10컬럼이라 메모리 부담이 작다.
- **대안**: 문자열 고정 스키마로 읽어 스키마 추론 1회를 아끼는 방법. 기각했다. 절약은 월당 1분 안팎이고, 결과가 달라질 위험이 있다.
- **비용**: 원본을 2번 읽는다(스키마 추론 1회 + 변환 1회).

## R3. 다른 달 행 차단 (FR-004)

- **결정**: Glue 진입 스크립트에서 다음 순서로 처리한다.
  1. Silver를 `persist`한다.
  2. `year`·`month`·`status`별 건수를 모은다.
  3. 입력 월과 다른 (`year`, `month`)가 하나라도 있으면 쓰기 전에 예외를 낸다. 예외 메시지에 그 건수를 담는다.
  4. Silver가 0행이면 같은 방식으로 실패시킨다.
- **이유**:
  - 동적 파티션 덮어쓰기는 결과에 나온 모든 달을 교체한다.
  - 이 검사는 C의 규칙 코드를 바꾸지 않고, 실행 진입점에서만 처리할 수 있다.
  - 모은 건수는 실행 기록(FR-010)에 그대로 쓴다.
- **현재 데이터**: 2026-11-09에 Athena로 확인했다. 36개월 원본에서 파일 월과 `m_time` 월이 다른 행은 0행이다. 그래도 2026-11 이후 새 월이 추가될 수 있어 이 검사는 유지한다.
- **대안**: 입력 월이 아닌 행을 걸러내고 쓰는 방법. 기각했다. 데이터를 말없이 버리게 된다(201 SC-001 "슬롯이 말없이 사라지지 않는다"와 충돌).

## R4. 쓰기: `build()` 대신 진입 스크립트에서 쓴다

- **결정**:
  - 진입 스크립트가 `tw_cems_spark.to_silver`를 부르고, `year`·`month` 파생과 쓰기를 직접 한다.
  - 파티션 식은 `tw_cems_spark.build`와 같다: `date_format(ts_local, 'yyyy')`, `'MM'`, `partitionBy("year","month")`, 동적 덮어쓰기.
- **이유**: `build()`는 읽기·변환·쓰기를 한 번에 해서 R2·R3 검사를 끼워 넣을 수 없다.
- **비용**: 파티션 식이 두 곳(C 모듈, 진입 스크립트)에 있게 된다.
  - 테스트로 두 결과의 파티션 값이 같은지 확인한다.
  - C에게 `build`를 `partitioned(silver)` + `write(...)`로 나누자고 제안할 수 있다. 이건 후속 작업이다.
- **대안**: C의 `scripts/glue_tw_cems_silver.py`를 고치는 방법. 기각했다. C의 검증 기록과 섞이고, 운영 진입점을 A가 관리하는 `services/` 아래에 두는 저장소 규칙과도 맞지 않는다.

## R5. 패키지 배포와 규칙 버전 (FR-010, FR-012)

- **결정**:
  - Terraform `archive_file`로 `src/` 아래 `smokestack_guard/__init__.py`와 `smokestack_guard/silver/`만 zip으로 묶는다.
  - zip은 원본 버킷 `ops/glue-packages/`에 올리고 `--extra-py-files`로 지정한다.
  - zip의 MD5를 Job 기본 인자 `--package_md5`로 넘겨 실행 기록에 남긴다.
- **이유**:
  - `tms-collection`의 Lambda가 이미 쓰는 방식이다(`archive_file`, `output_file_mode = "0666"`).
  - 코드가 바뀌면 해시가 바뀌어 `apply` 때 다시 올라간다.
  - 실행 기록의 해시로 어떤 코드가 돌았는지 알 수 있다. 커밋은 그 해시를 올린 PR로 추적한다.
  - `smokestack_guard/data/__init__.py`는 없는 모듈(`collector`)을 import하므로 zip에서 뺀다.
- **대안**: git 커밋 SHA를 기록하는 방법. 기각했다. Terraform이 커밋을 알 수 없고, 로컬 작업 트리가 적용된 코드와 다를 수 있다.
- **spec 반영**: FR-010의 "규칙 코드의 버전(커밋)"을 "버전(패키지 해시)"으로 고친다.

## R6. 카탈로그: Terraform 테이블 + 파티션 프로젝션

- **결정**:
  - `aws_glue_catalog_table`로 `tms_silver.tw_cems`를 코드로 정의한다.
  - 컬럼과 타입은 C의 계약대로 둔다.
  - 파티션 프로젝션을 쓴다: `year` 정수 2023~2030, `month` 정수 1~12, 2자리.
- **이유**:
  - 크롤러가 타입을 추정하지 않으므로 계약 타입이 고정된다(FR-006).
  - 새 월(2026-11 등)이 생겨도 크롤러나 `MSCK REPAIR` 없이 Athena에서 바로 보인다.
- **한계**:
  - 프로젝션은 Athena만 이해한다. Spark에서 카탈로그로 이 테이블을 읽으면 파티션이 보이지 않는다.
  - 005(ML-ready)와 E는 S3 경로(`s3://.../silver/tw_cems/`)로 직접 읽는다. 이 점을 계약 문서에 적는다.
- **대안**: `tms-eda`처럼 수동 크롤러를 쓰는 방법. 기각했다. 타입이 추정되고, 새 월마다 사람이 크롤러를 돌려야 한다.

## R7. 조회용 Athena 워크그룹: 기존 `tms-eda`를 쓴다 (2026-11-09 사용자 결정)

- **결정**: 새 워크그룹을 만들지 않는다. `tms-eda` 워크그룹(결과는 EDA 버킷 `athena-results/`, 30일 만료, 쿼리당 10GB 한도)에서 `tms_silver` DB를 조회한다.
- **이유**:
  - Silver가 원본 버킷에 있어서, 결과를 원본 버킷에 두면 수명 주기 규칙 없이 계속 쌓인다(R11).
  - EDA 버킷에 두는 것은 **쿼리 결과뿐**이다. Silver 데이터는 두지 않는다.
- **비용**: Silver 조회가 `tms-eda` 스택의 워크그룹에 의존한다.
  - Terraform 참조로 묶지는 않고, 문서로만 의존한다.
  - EDA 스택을 정리할 때 Silver 조회용 워크그룹을 따로 만든다.
- **대안**:
  - 원본 버킷 `ops/athena-results/`에 결과를 두는 방법: 기각. 결과가 쌓이고 사람이 지워야 한다.
  - 새 Silver 버킷을 만드는 방법: 기각(R10).

## R8. 일괄 실행 명령: `run_backfill.py`를 복사해 고친다

- **결정**: `services/tms-silver/run_silver.py`는 `services/tms-eda/run_backfill.py`의 구조를 가져와 쓰고, 아래만 바꾼다.

  | 항목 | `run_backfill.py` (EDA) | `run_silver.py` (Silver) |
  |---|---|---|
  | 완료 판단 | `_SUCCESS` | 실행 기록 `silver/_runs/tw_cems/YYYY-MM.json` 존재 |
  | 결과 표 | 상태·시간·비용 | 실행 기록의 Silver 행 수와 `ok` 행 수를 더함 |
  | 크롤러 시작 | 있음 | 없음 |
  | 기본값 | EDA Job·버킷 | Silver Job·버킷 |

  기존에 쓰던 동작은 그대로 유지한다: 범위 지정, 미리 보기, `--only-missing`, 동시 실행 제한, 1회 재시도, 동시 실행 거절 대기, 비용 추정.
- **이유**:
  - 동적 파티션 덮어쓰기에서 `_SUCCESS`는 파티션 안이 아니라 출력 루트(`silver/tw_cems/_SUCCESS`)에 하나만 생긴다. 그래서 월별 완료 판단을 실행 기록으로 바꿔야 한다.
  - `services/*`는 서로 import하는 패키지가 아니다.
- **비용**: 약 300줄이 중복된다. 공통 모듈로 빼는 것은 세 번째 사용처가 생길 때 한다.

## R9. 규모·비용 추정

- **입력**: 36개 파일 약 85GB, 1억 5,972만 행(월 평균 약 440만 행, 2.4GB).
- **출력**: 8,036만 행. Parquet으로 월 수십 MB, 전체 수 GB 이하로 예상한다.
- **Job 설정**: G.1X 10워커, 동시 6개, 제한 시간 60분. 이 값은 `tms-eda`와 같은 틀이다.
- **비용(추정)**:
  - 월당 약 5~10분, 36개월 합계 30~60 DPU시간이다.
  - DPU시간당 $0.308(`run_backfill.py`와 같은 단가)로 계산하면 **약 $10~20**이다.
  - 첫 한 달 실행 뒤 실측으로 고친다.
- **실측 (2026-11-09)**: 월당 94~153초(시작 대기 포함), 1,000~1,500 DPU초, 약 $0.10. 36개월 합계 약 $3.8(단가 $0.308 기준). 추정의 1/3 수준이다. 실제 계산은 월 70초 안팎이고 나머지는 Glue 시작 대기다.
- **S3·Athena**: Silver 수 GB 저장(원본 버킷, 이전 버전 포함, R11)과 쿼리 비용은 월 $1 미만이다.

## R10. 저장 위치와 Silver 경로 규칙: 원본 버킷의 `silver/` (2026-11-09 사용자 결정)

- **결정**: 새 버킷을 만들지 않는다. 원본 버킷 `smokestack-tms-raw-952900391026`에 아래 경로를 쓴다. EDA 버킷에는 Silver를 두지 않는다.

  ```
  s3://smokestack-tms-raw-952900391026/
  ├── tms_cleansys/                 기존 K-TMS 수집 원본 (접근 안 함)
  ├── bronze/tw_cems/historical/    기존 대만 원본 (읽기만)
  ├── silver/
  │   ├── tw_cems/year=YYYY/month=MM/    004
  │   ├── tw_cems_ml_ready/              005
  │   ├── ktms/, ktms_ml_ready/          나중 (CleanSYS)
  │   └── _runs/<테이블>/YYYY-MM.json    월 실행 기록
  └── ops/
      ├── glue-scripts/             Glue 진입 스크립트
      └── glue-packages/            smokestack_guard.zip
  ```

- **팀 규칙** (`AGENTS.md`에 추가):
  1. 경로 `silver/<테이블>/`과 카탈로그 `tms_silver.<테이블>`의 이름을 같게 한다.
  2. 테이블 이름은 `<출처>[_<용도>]`이다.
     - 출처: `tw_cems`(대만 CEMS), `ktms`(국내 CleanSYS). 출처가 다르면 같은 테이블에 섞지 않는다.
     - 용도: 붙이지 않으면 정제 테이블, `_ml_ready`는 피처·라벨 테이블이다.
  3. 파티션은 기본 `year=YYYY/month=MM`(출처의 현지 시각 기준)이다. 다르게 하려면 그 테이블 계약에 적는다.
  4. `_`로 시작하는 폴더는 테이블이 아니다(실행 기록 등).
  5. 실행 역할마다 쓰기·삭제 권한을 자기 테이블 경로(`silver/<테이블>/*`, `silver/_runs/<테이블>/*`)에만 준다.
  6. `bronze/`, `tms_cleansys/`에 쓰는 권한은 수집 주체만 가진다.
- **이유**:
  - 원본·Silver를 한 버킷에서 계층(`bronze/`, `silver/`)으로 나눈다(사용자 결정).
  - 버킷을 늘리지 않는다.
  - K-TMS 등 Silver가 늘어날 때 같은 규칙을 따른다.
- **위험과 완화**:
  - 원본 버킷에 삭제 권한을 가진 실행 주체가 처음 생긴다. 권한을 경로 단위로 좁히고(R12), 원칙 I에 따라 **B를 PR 리뷰어**로 넣는다.
  - 원본 버킷 설정(`tms-collection` 스택, `raw-archive` 모듈)은 바꾸지 않는다. Silver 스택은 버킷을 `data`로 이름만 참조한다.
- **대안**:
  - 새 Silver 버킷: 권장했으나 사용자가 기각했다(버킷을 늘리지 않음).
  - EDA 버킷: 기각했다. EDA는 탐색용 사본이다(003).

## R11. 수명 주기 규칙 없음, 임시 경로 없음

- **결정**:
  - 원본 버킷에 수명 주기 규칙을 추가하지 않는다(원칙 I, `raw-archive` 모듈 주석).
  - Glue Job에 `--TempDir`을 주지 않는다. Parquet 쓰기에는 필요 없다.
  - Athena 결과는 R7대로 EDA 버킷에 둔다.
- **결과**: 같은 월을 다시 실행하면 교체된 이전 Parquet이 **이전 버전으로 계속 남는다.**
  - Silver 전체가 수 GB 규모라, 36개월을 모두 다시 실행해도 수 GB가 늘어나고 비용은 월 $0.1 수준이다.
  - 정리가 필요하면 사람이 `silver/` 경로의 이전 버전만 지운다.

## R12. 원본 버킷 권한 범위

| 동작 | 경로 | 이유 |
|---|---|---|
| `s3:ListBucket` (`s3:prefix` 조건) | `bronze/tw_cems/*`, `silver/tw_cems`, `silver/tw_cems/*`, `silver/_runs/tw_cems/*` | 입력 목록, 덮어쓰기 전 기존 파티션 목록 |
| `s3:GetObject` | `bronze/tw_cems/*`, `ops/glue-scripts/*`, `ops/glue-packages/*` | 입력, 스크립트, 패키지 |
| `s3:GetObject`, `PutObject`, `DeleteObject`, `AbortMultipartUpload` | `silver/tw_cems/*`, `silver/_runs/tw_cems/*` | 파티션 교체, 실행 기록 |

- `tms-eda`에서는 Spark 덮어쓰기가 경로 끝에 `/`가 없는 형태로도 목록을 조회해, 버킷 전체 목록 권한을 줬다. 원본 버킷에는 버킷 전체 목록 권한을 주지 않는다. 그래서 끝 `/`가 없는 `silver/tw_cems`를 조건에 넣었다.
- **폴더 표시 파일 (2026-11-09 첫 실행에서 확인)**: Glue(EMRFS)는 Parquet을 쓸 때 상위 경로마다 0바이트 `<경로>_$folder$` 파일을 만든다. 첫 실행이 `silver_$folder$`에 대한 `PutObject` 거부로 실패했다(읽기·변환·월 검사는 통과).
  - `silver/tw_cems/` 아래 표시는 기존 권한에 포함된다.
  - 그 위의 `silver_$folder$`, `silver/tw_cems_$folder$` 두 키만 정확히 허용했다(`WriteSilverFolderMarkers`). `silver/*`로 넓히지 않는다.
  - 005 등 다른 Silver 테이블도 같은 방식으로 `silver/<테이블>_$folder$`를 허용해야 한다.
- 첫 실행에서 목록 조회가 거부되면(`AccessDenied` on `ListBucket`), 로그에서 실제 조회한 접두어를 확인하고 그 접두어만 추가한다. 쓰기 권한은 넓히지 않는다.
