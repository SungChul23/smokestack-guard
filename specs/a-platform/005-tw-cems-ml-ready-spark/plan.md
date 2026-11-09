# Implementation Plan: TW CEMS ML-ready Spark 이식

**Branch**: `32-a-tw-cems-ml-ready-spark-이식-silvertw_cems-silvertw_cems_ml_ready` | **Date**: 2026-11-09 | **Spec**: [spec.md](spec.md) | **Issue**: #32

**Input**: Feature specification from `specs/a-platform/005-tw-cems-ml-ready-spark/spec.md`

## Summary

C의 pandas ML-ready 규칙(`ml_ready.to_ml_ready`)을 Spark로 옮긴다.
- **방법**: 굴뚝·항목별 **슬롯 번호(30분 단위 정수) + 범위 윈도우(`rangeBetween`)**를 쓴다. 빈 칸을 채우지 않고도 pandas와 같은 의미를 얻는다(R1·R2).
- **코드**: 규칙은 `services/tms-silver/ml_ready_spark.py`에 둔다. 상수는 C의 `ml_ready.py`에서 import하고, C의 `src/`는 수정하지 않는다. 입력 정규화는 분리해 K-TMS(시나리오 B)에서도 쓸 수 있게 한다(R3).
- **실행**: Glue 5.0 Job 하나에 `build`·`compare` 두 모드를 둔다.
  - `build`: `silver/tw_cems/` 36개월을 읽는다. `measured_at` 범위로 6개 파일을 정렬해 `silver/tw_cems_ml_ready/`에 전체 덮어쓴다(R4).
  - `compare`: C의 결과 파일과 35컬럼을 전부 비교한다(R5·R6).
- **역할**: 새로 만들고 자기 경로에만 쓴다(R9).
- **실패 판별**: `latest.json`이 없으면 실패 또는 진행 중이다(R7).

## Technical Context

**Language/Version**: Python 3.11 (Glue 5.0), Terraform `~> 1.15.0`

**Primary Dependencies**:
- Glue 런타임: PySpark 3.5.4, boto3, pandas·numpy(`ml_ready.py` import용, Glue 기본 포함 확인됨: pandas 2.2.2)
- 로컬 dev: `services/tms-silver/pyproject.toml` 그대로(pyspark 3.5.4, pandas 2.2.3, numpy<2, pyarrow 16.1.0, pytest, ruff)

**Storage**:
- 읽기: `silver/tw_cems/`(004), C의 `smokestack-cems-local-eda-952900391026/ml_ready/part.parquet`
- 쓰기: `silver/tw_cems_ml_ready/`, `silver/_runs/tw_cems_ml_ready/`

**Testing**: pytest + 로컬 Spark 3.5.4. 정답지는 같은 fixture에 실행한 pandas `to_ml_ready`. boto3는 mock. Terraform은 `fmt`/`validate`(plan은 사용자).

**Target Platform**: AWS ap-northeast-2 (Glue 5.0, Athena), 로컬 WSL

**Project Type**: 배치 변환 규칙 + Glue 진입점 + 운영 CLI + IaC

**Performance Goals**: 1회 15분 이내(제한 60분)

**Constraints**:
- C의 코드 수정 금지
- 피처·라벨 정의 변경 금지
- Silver(`silver/tw_cems/`) 쓰기 금지
- 원본(`bronze/`, `tms_cleansys/`) 접근 금지
- 에이전트의 AWS·Terraform 실행 금지(`fmt`/`validate` 제외)

**Scale/Scope**: 입력 8,036만 행 → 대상 약 1,769만 행, 출력 약 924MB, 굴뚝×항목 수백 그룹

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| 원칙 | 판정 | 근거 |
|---|---|---|
| I. 수집 연속성 | ✅ | 수집 스택·원본 경로를 건드리지 않는다. 새 역할은 `bronze/`·`tms_cleansys/`에 접근 권한이 없다. 원본 버킷 설정 변경도 없다. |
| II. 비밀값 비공개 | ✅ | 비밀값이 없다. 로그와 실행 기록에는 건수·경로·버전만 남긴다. 비교 결과에도 값 대신 키만 남긴다. |
| III. 코드로, 적용은 사람이 | ✅ | 모든 리소스를 Terraform으로 만든다. `plan`과 `apply`는 사용자가 한다(사용자 결정). 권한은 아래 표의 최소 범위다. |
| IV. 데이터 계약 우선 | ✅ | 35컬럼 계약은 C의 `ml_ready.py` 그대로다(상수 import). 저장·조회 계약은 [contracts/tw-cems-ml-ready-table.md](contracts/tw-cems-ml-ready-table.md)에 둔다. 계약 변경(`observed_risk_level` 등)은 범위 밖이다. 계산 의미는 PR에서 C가 리뷰한다(CODEOWNERS A+C). |
| V. 같은 조건의 정직한 비교 | ✅ | 이 기능의 핵심이다. pandas와 35컬럼 전부 일치를 확인한다(로컬 테스트 + 실데이터 compare). 시나리오 B를 위해 K-TMS도 같은 코드를 쓰도록 정규화를 분리한다. |
| VI. 설명 가능한 결과 | ✅ | 실행 기록에 단계별 행 수, 양성 수, 중복 수, 코드 버전을 남긴다. 비교 기록에 컬럼별 불일치 수를 남긴다. |
| 운영 제약: 비용 | ✅ | build 1회, compare 1회 각각 약 $0.3~0.5(R8). 새 버킷·워크그룹은 없다. |
| 운영 제약: 외부 패키지 | ✅ | 추가하지 않는다. |

**부여 권한** (새 역할 `tms-glue-silver-ml-ready`, R9)

| 동작 | 대상 | 이유 |
|---|---|---|
| `AWSGlueServiceRole` | 카탈로그, 로그, 지표 | Job 실행 기본 |
| `s3:ListBucket` (prefix 조건) | 원본 버킷: `silver/tw_cems`, `silver/tw_cems/*`, `silver/tw_cems_ml_ready`, `silver/tw_cems_ml_ready/*`, `silver/_runs/tw_cems_ml_ready/*` | 입력 목록, 덮어쓰기 전 목록 |
| `s3:GetObject` | 원본 버킷: `silver/tw_cems/*`, `ops/glue-scripts/*`, `ops/glue-packages/*` | 입력, 스크립트, 패키지 |
| `s3:GetObject`, `PutObject`, `DeleteObject`, `AbortMultipartUpload` | 원본 버킷: `silver/tw_cems_ml_ready/*`, `silver/_runs/tw_cems_ml_ready/*` | 전체 덮어쓰기, 실행 기록 |
| `s3:GetObject`, `PutObject`, `DeleteObject` | 원본 버킷: `silver/tw_cems_ml_ready_$folder$` | Glue 폴더 표시 파일(004에서 확인) |
| `s3:GetObject`, `PutObject` | 원본 버킷: `silver_$folder$` | 상위 표시 파일. 삭제 권한은 주지 않는다 |
| `s3:ListBucket` (prefix `ml_ready/*`), `s3:GetObject` | `smokestack-cems-local-eda-952900391026/ml_ready/*` | compare 정답지 읽기만 |

`silver/tw_cems/`에는 쓰기 권한이 없다. 004 역할(`tms-glue-silver`)은 그대로 두고 바꾸지 않는다.

**Phase 1 뒤 재점검**: data-model과 contracts에 원칙 위반이 없다. 통과.

## Project Structure

### Documentation (this feature)

```text
specs/a-platform/005-tw-cems-ml-ready-spark/
├── spec.md
├── plan.md                              # 이 파일
├── research.md                          # R1~R10
├── data-model.md                        # 입력·출력 35컬럼·실행 기록
├── quickstart.md
├── contracts/
│   ├── run-interface.md                 # Glue Job 인자(build/compare), run_ml_ready.py
│   └── tw-cems-ml-ready-table.md        # 저장·조회 계약
├── checklists/requirements.md
└── tasks.md                             # /speckit-tasks
```

### Source Code (repository root)

```text
services/tms-silver/
├── ml_ready_spark.py                    # 새로: normalize / add_features / to_ml_ready (규칙)
├── glue_tw_cems_ml_ready.py             # 새로: Glue 진입점 (--mode build|compare)
├── run_ml_ready.py                      # 새로: 실행 명령 (run_silver의 estimate_cost 재사용)
├── README.md                            # ML-ready 절 추가
└── tests/
    ├── fixtures/ml_ready/               # 새로: 가짜 Silver (공백·월 경계·진입 사례)
    ├── test_ml_ready_spark.py           # pandas to_ml_ready와 35컬럼 비교, 행 기준 lag와의 차이
    ├── test_glue_tw_cems_ml_ready.py    # 파일 수·정렬·latest.json·compare
    └── test_run_ml_ready.py             # boto3 mock

infra/stacks/tms-silver/
├── main.tf                              # 역할·정책·스크립트 2개·Job·카탈로그 테이블 추가 (004 리소스는 그대로)
├── variables.tf                         # ml_ready_worker_count, reference 경로
└── outputs.tf                           # ml-ready Job·역할·테이블 출력 추가

src/smokestack_guard/silver/ml_ready.py  # C의 코드. 읽기만 (상수 import)
```

**Structure Decision**:
- 004와 같은 스택과 폴더에 더한다. 규칙 코드도 A의 `services/tms-silver/`에 둔다(사용자 결정).
- C의 `ml_ready.py`가 바뀌면(#30 등) 상수는 자동으로 따라온다. 계산 로직이 바뀌면 이 모듈도 고쳐야 한다. CI(`tms-silver.yml`)가 `src/smokestack_guard/silver/**` 변경 때도 돌기 때문에, pandas와의 비교 테스트가 차이를 잡는다.

## Complexity Tracking

원칙 위반은 없다. 의도적으로 감수한 것만 적는다.

| 감수한 것 | 이유 | 더 단순한 대안을 쓰지 않은 이유 |
|---|---|---|
| 같은 규칙을 pandas(C)와 Spark(A) 두 곳에 구현 | 클라우드에서 Spark로 실행(이슈 #32 결정 1), C의 코드는 수정하지 않음(사용자 결정) | `applyInPandas`로 pandas를 그대로 돌리면 한 곳이지만, Spark 구현을 쓰기로 했다. 대신 CI에서 pandas와 항상 비교한다 |
| 역할 하나를 더 만듦 (`tms-glue-silver-ml-ready`) | 테이블마다 자기 경로에만 쓰는 규칙(AGENTS.md S3 경로 규칙 5) | 004 역할을 넓히면 Silver Job이 ML-ready를 지울 수 있게 된다 |
| compare 모드가 Terraform 밖 버킷(C의 버킷)을 읽음 | 실데이터 정답지가 거기 있음 | 정답지를 다시 만들려면 pandas 36개월을 다시 돌려야 한다(메모리 부족으로 C의 PC에서만 가능했음) |

## 실행 결과 (2026-11-09)

- **적용**: 사용자가 `terraform apply`를 실행했다(생성 7). 이후에는 진입 스크립트와 규칙 모듈만 다시 올린다(compare 허용 오차 수정).
- **build**

  | 항목 | 값 | 기준 |
  |---|---|---|
  | Silver 입력 | 80,359,440 | 004 |
  | 대상 선택 = 출력 행 | 17,643,361 | C 최신(monthly-counts.md)과 같음 |
  | 중복 키 | 0 | |
  | 학습 가능 양성 | 133,726 (NOx 106,941, SO₂ 26,785) | C 최신과 같음 |
  | 파일 | 6개, 215~266MB, 합계 1.4GiB | C의 pandas 파일 924MB보다 크다. 파일 안을 시각 순으로 정렬해 압축률이 낮기 때문이며, 사용에는 문제없다 |

- **compare** (C의 최신 정답지, 실행 118초, $0.10)
  - 행·키가 완전히 일치한다.
  - 34컬럼은 불일치 0이다.
  - `ratio_rolling_std_3h`만 21,739행이 다르다. 부동소수점 잔여로 확인했고 허용 오차를 조정했다(research R5).
- **처음 compare** (이전 정답지): 2023-11·12 입력 버전 차이로 45,859행이 달랐다(research R5).
- **compare (허용 오차 반영 후, 실행 119초, $0.10)**: **`passed=True`**
  - 행 17,643,361 = 17,643,361, 한쪽에만 있는 키 0
  - 컬럼별 최대 차이
    - `ratio_rolling_std_3h` 5.96e-06 (허용 1e-5 안)
    - `ratio_rolling_mean_1h` 8.24e-13, `ratio_rolling_mean_3h` 2.27e-13
    - `hour_sin`, `month_sin` 1.11e-16
    - 나머지 컬럼은 차이 0
- **남은 확인**
  - build 재실행(SC-004)
  - Athena 조회(SC-006)
  - E 확인(SC-008)
