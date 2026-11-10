# Implementation Plan: TW CEMS Silver 클라우드 실행 (Glue, 36개월)

**Branch**: `28-a-tw-cems-silver-glue-실행-36개월-원본-버킷-silver` | **Date**: 2026-11-09 | **Spec**: [spec.md](spec.md) | **Issue**: #28

**Input**: Feature specification from `specs/a-platform/004-tw-cems-silver-glue/spec.md`

## Summary

새 스택 `infra/stacks/tms-silver`에 아래 리소스를 만든다. 새 버킷과 워크그룹은 만들지 않는다.
- Glue 5.0 Job `tms-silver-tw-cems`와 실행 역할
  - 원본 버킷 `bronze/tw_cems/`는 읽기만 한다.
  - 쓰기는 `silver/tw_cems/`와 그 실행 기록 경로에만 한다.
- 원본 버킷 `ops/`에 진입 스크립트와 `smokestack_guard` 패키지 zip 업로드
- 카탈로그 DB·테이블 `tms_silver.tw_cems` (파티션 프로젝션)
- Glue 로그 그룹

Silver는 원본 버킷의 `silver/` 경로에 둔다(R10, 사용자 결정). 조회는 기존 `tms-eda` 워크그룹으로 한다(R7). 팀 공통 Silver 경로 규칙은 `AGENTS.md`에 추가한다.

진입 스크립트 `services/tms-silver/glue_tw_cems_silver.py`는 C의 `tw_cems_spark`(`read_raw`, `to_silver`)를 **수정 없이** 부른다. 쓰기 전에 다른 달 행과 0행을 검사하고, 그 달 파티션만 동적 덮어쓰기한다. 쓰기가 끝나면 월 실행 기록을 남긴다.

사용자는 `services/tms-silver/run_silver.py`로 한 달을 시험 실행한 뒤 36개월(2023-11~2026-10)을 돌리고, Athena로 확인한다.

## Technical Context

**Language/Version**:
- Python 3.11 (Glue 5.0 런타임)
- 로컬 Spark 테스트: Docker `sg-spark:3.5` (Spark 3.5.4, Java 17)
- Terraform `~> 1.15.0`

**Primary Dependencies**:
- Glue 런타임: PySpark 3.5.4, boto3. pandas·numpy는 상수 import 때문에 설치만 필요(Glue 5.0 기본 포함으로 예상, R1)
- 규칙 코드: `src/smokestack_guard/silver/tw_cems.py`, `tw_cems_spark.py` (C, 수정 없음)
- 로컬 dev: `pyspark==3.5.4`, `pandas==2.2.3`, `numpy<2`, `pyarrow==16.1.0`, `boto3`, `pytest`, `ruff`
- provider: `aws ~> 6.0`, `archive ~> 2.0` (`tms-collection`과 같음)

**Storage**:
원본 버킷 `smokestack-tms-raw-952900391026` 하나만 쓴다(R10). 버전 관리는 켜져 있고 수명 주기 규칙은 없다(R11).

| 경로 | 내용 | 이 기능의 권한 |
|---|---|---|
| `tms_cleansys/` | K-TMS 수집 원본 (기존) | 없음 |
| `bronze/tw_cems/` | 대만 원본 (기존) | 읽기 |
| `silver/tw_cems/` | Silver 데이터 | 읽기·쓰기·삭제 |
| `silver/_runs/tw_cems/` | 월 실행 기록 | 읽기·쓰기·삭제 |
| `ops/glue-scripts/`, `ops/glue-packages/` | 진입 스크립트, 패키지 zip (Terraform이 올림) | 읽기 |

- 005에서 `silver/tw_cems_ml_ready/`를 추가한다.
- Athena 결과는 `tms-eda` 워크그룹의 EDA 버킷 `athena-results/`에 저장된다(30일 만료, R7).

**Testing**:
- 일괄 실행 명령: pytest, boto3는 mock
- 진입 스크립트 검사 로직: Docker 로컬 Spark에서 pytest
- Terraform: `fmt`, `validate`, `plan`
- 상세: [quickstart.md](quickstart.md)

**Target Platform**: AWS `ap-northeast-2` (Glue 5.0, Athena), 로컬 WSL + Docker

**Project Type**: 인프라 스택(IaC) + 배치 실행 진입점 + 운영 CLI

**Performance Goals**: 월당 15분 이내(제한 시간 60분). 36개월을 동시 6개로 1시간 안팎(추정, R9).

**Constraints**:
- 원본 쓰기·삭제 금지
- C의 규칙 코드 수정 금지
- 다른 달 파티션 변경 금지
- 기존 스택(`tms-collection`, `tms-eda`) 변경 금지
- AI 에이전트는 AWS에 대해 실행하지 않음(`plan`까지만)

**Scale/Scope**:
- 입력: 36개 파일, 약 85GB, 1억 5,972만 행(월 평균 약 440만 행)
- 출력: 약 8,036만 행. 수 GB 이하 예상

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| 원칙 | 판정 | 근거 |
|---|---|---|
| I. 수집 연속성 | ✅ (조건부) | 수집 스택·스케줄과 원본 버킷 설정은 손대지 않는다. 버킷은 `data`로 이름만 참조하고, 수명 주기 규칙도 추가하지 않는다. 다만 **원본 버킷에 삭제 권한을 가진 첫 실행 주체**가 생긴다(Silver 덮어쓰기). 완화책은 두 가지다. ① 쓰기·삭제를 `silver/tw_cems/*`, `silver/_runs/tw_cems/*`로만 좁힌다(R12). ② 원칙 I의 "팀 확인"으로 **B를 PR 리뷰어**로 넣는다. `bronze/`와 `tms_cleansys/`에는 쓰기 권한이 없다. |
| II. 비밀값 비공개 | ✅ | API 키가 필요 없다. 자격증명은 실행자 프로필에서 읽는다. 로그와 실행 기록에는 건수·경로·버전만 남기고 데이터 값은 남기지 않는다. |
| III. 코드로, 적용은 사람이 | ✅ | 모든 리소스를 Terraform으로 만든다. 에이전트는 `plan`까지만 한다. Job 실행은 사용자가 한다. 권한은 아래 표의 최소 범위다. |
| IV. 데이터 계약 우선 | ✅ | Silver 스키마·의미는 C의 계약(201)을 그대로 쓴다. 저장·조회 계약은 [contracts/tw-cems-silver-table.md](contracts/tw-cems-silver-table.md)에 둔다. 계약 변경은 없다. 진입 스크립트가 C의 파티션 식을 다시 쓰므로(R4) **C를 PR 리뷰어로 넣는다.** |
| V. 같은 조건의 정직한 비교 | 해당 없음 | 규칙·모델 비교가 아니다. pandas 결과와의 비교는 후속 작업이다. |
| VI. 설명 가능한 결과 | ✅ | 월 실행 기록에 입력·출력 건수, `status` 분포, 실행한 패키지 해시, 런타임 버전을 남겨 Silver가 어떤 코드·입력으로 만들어졌는지 추적할 수 있다. |
| 운영 제약: 비용 | ✅ | 36개월 1회 실행에 약 $10~20(Glue)이 든다. 새 버킷·워크그룹이 없고, 저장·조회는 월 $1 미만이다(추정, R9·R11). 첫 달 실측으로 고친다. |
| 운영 제약: 외부 패키지 | ✅ | 추가 없음. Glue 기본 pandas가 import되지 않을 때만 `--additional-python-modules pandas`를 쓴다(R1). |

**부여 권한** (역할 `tms-glue-silver`)

| 권한 | 대상 | 이유 |
|---|---|---|
| `AWSGlueServiceRole` (관리형) | Glue 카탈로그, `/aws-glue/*` 로그, 지표 | Job 실행 기본. `tms-eda`와 같다 |
| `s3:ListBucket` (`s3:prefix` 조건) | 원본 버킷: `bronze/tw_cems/*`, `silver/tw_cems`, `silver/tw_cems/*`, `silver/_runs/tw_cems/*` | 입력 목록, 덮어쓰기 전 기존 파티션 목록. 버킷 전체 목록 권한은 주지 않는다(R12) |
| `s3:GetObject` | 원본 버킷: `bronze/tw_cems/*`, `ops/glue-scripts/*`, `ops/glue-packages/*` | 입력, 스크립트, 패키지 읽기 |
| `s3:GetObject`, `PutObject`, `DeleteObject`, `AbortMultipartUpload` | 원본 버킷: `silver/tw_cems/*`, `silver/_runs/tw_cems/*` | 파티션 교체, 실행 기록 |

`silver/tw_cems_ml_ready/`와 다른 Silver 경로에는 권한을 주지 않는다. 005가 자기 Job에 따로 준다.

**Phase 1 뒤 재점검**: 설계 문서(data-model, contracts)에 원칙 위반이 없다. 통과.

## Project Structure

### Documentation (this feature)

```text
specs/a-platform/004-tw-cems-silver-glue/
├── spec.md
├── plan.md                         # 이 파일
├── research.md                     # R1~R9 결정
├── data-model.md                   # 원본 키, Silver 타입, 실행 기록
├── quickstart.md                   # 검증 절차
├── contracts/
│   ├── run-interface.md            # Glue Job 인자, run_silver.py
│   └── tw-cems-silver-table.md     # 저장 위치·조회 방법
├── checklists/requirements.md
└── tasks.md                        # /speckit-tasks
```

### Source Code (repository root)

```text
infra/stacks/tms-silver/            # 새 스택 (tms-eda 구성을 따름)
├── backend.tf                      # key = stacks/tms-silver/terraform.tfstate
├── versions.tf                     # aws ~> 6.0, archive ~> 2.0, default_tags stack = tms-silver
├── variables.tf                    # 원본 버킷 이름, 워커 수
├── main.tf                         # 역할·스크립트·패키지·Job·카탈로그·로그 (버킷·워크그룹 없음)
├── outputs.tf
└── .terraform.lock.hcl

services/tms-silver/                # 새 폴더 (CODEOWNERS: A + C, 원본 버킷 권한 때문에 PR 리뷰에 B 포함)
├── glue_tw_cems_silver.py          # Glue 진입 스크립트 (검사·쓰기·실행 기록)
├── run_silver.py                   # 일괄 실행 명령 (run_backfill.py 기반, R8)
├── pyproject.toml                  # dev 의존성: Spark 3.5.4 계열
├── README.md
└── tests/
    ├── test_glue_tw_cems_silver.py # 로컬 Spark (Docker)
    └── test_run_silver.py          # boto3 mock

src/smokestack_guard/silver/        # C의 코드, 읽기만 (zip으로 배포)
.github/CODEOWNERS                  # /services/tms-silver/, /infra/stacks/tms-silver/ 추가
AGENTS.md                           # 저장소 구조에 tms-silver 추가, "S3 경로 규칙" 절 추가 (R10)
```

**Structure Decision**:
- `tms-eda`와 같은 틀(스택 + `services/<기능>`)을 쓴다.
- 운영 진입점은 A가 관리하는 `services/tms-silver/`에 둔다. C의 `scripts/glue_tw_cems_silver.py`는 C의 검증 기록으로 두고 고치지 않는다.
- 규칙 코드는 `src/`에서 그대로 zip으로 묶어 저장소에 사본을 두지 않는다.

## Complexity Tracking

원칙 위반은 없다. 의도적으로 감수한 중복 두 가지만 적는다.

| 중복 | 이유 | 더 단순한 대안을 쓰지 않은 이유 |
|---|---|---|
| 파티션 식(`year`·`month`)이 C 모듈과 진입 스크립트 두 곳에 있음 | 쓰기 전에 다른 달 검사를 끼워야 함(R3·R4) | `build()`를 쓰면 검사를 끼울 수 없다. C 모듈을 고치는 것은 범위 밖이다(C에게 분리 제안). 두 결과가 같은지는 테스트로 확인한다 |
| `run_silver.py`가 `run_backfill.py`와 약 300줄 겹침 | 완료 판단·결과 표가 다름(R8) | `services/*`는 서로 import하지 않는다. 공통 모듈은 세 번째 사용처가 생기면 만든다 |

## 실행 결과 (2026-11-09)

**적용**: 사용자가 `terraform apply`(생성 9). 첫 실행 뒤 정책 1개 수정(폴더 표시 파일), 진입 스크립트 1개 수정(월당 파일 1개).

**첫 실행에서 고친 것**
| 증상 | 원인 | 조치 |
|---|---|---|
| 2025-10 `FAILED` (`s3:PutObject` 거부, `silver_$folder$`) | Glue(EMRFS)가 상위 경로에 0바이트 폴더 표시 파일을 만든다 | `silver_$folder$`, `silver/tw_cems_$folder$` 두 키만 허용(R12) |
| 한 달 Parquet 36개(파일당 약 0.4MB) | 집계 뒤 조각 수대로 파일이 생김 | 쓰기 직전 `coalesce(1)`. 한 달 약 16MB → 파일 1개 |

**36개월 실행** (`run_silver.py`, 동시 6, 실패 0, 재시도 0)

| 항목 | 값 | 기준 | 판정 |
|---|---|---|---|
| 성공 월 | 36 / 36 | SC-001 | ✅ |
| 입력 줄 수 | 159,725,257 | `tms_eda.tw_cems_raw` 159,725,257 | ✅ 일치 |
| Silver 행 | 80,359,440 | C의 pandas 결과 8,036만 | ✅ 일치 (SC-002) |
| `ok` 행 | 24,743,836 | | |
| 월당 실행 | 94~153초, 1,000~1,500 DPU초 | | |
| Glue 비용 | 35개월 41,201 DPU초 ≈ $3.5(단가 $0.308) + 2025-10 시도 3회 ≈ $0.3 | R9 추정 $10~20 | 실제 청구액은 Cost Explorer로 확인 (SC-006) |
| 원본 무변경 | 전후 모두 39개, 91,413,965,014바이트 (`bronze/tw_cems/historical/`, zip 3개 포함) | SC-005 | ✅ |
| 카탈로그 타입 | `SHOW CREATE TABLE` 결과가 data-model.md §2와 같음 | FR-006 | ✅ |

- 남은 확인: Athena 월별 행 수(36행)·월 조건 스캔량(SC-003), 권한 시뮬레이터(quickstart §8), C·D·E 조회 확인(SC-007).
- pandas 결과와의 전체 비교는 범위 밖이다. C의 결과는 `s3://smokestack-cems-local-eda-952900391026/cems_silver/part.parquet`(573MB), `ml_ready/part.parquet`(924MB)에 있다.
