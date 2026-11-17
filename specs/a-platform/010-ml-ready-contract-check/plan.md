# Implementation Plan: K-TMS ML-ready 계약 검사 단계

**Branch**: `46-a-k-tms-silverml-ready-매일-갱신-파이프라인-glue-iceberg-silver2` | **Date**: 2026-11-17 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/a-platform/010-ml-ready-contract-check/spec.md`

## Summary

008의 Step Functions `tms-silver2-ktms`에 ML-ready 다음 단계로 **검사 Lambda** 하나를 붙인다. Lambda는 같은 실행의 ML-ready 실행 기록에서 범위와 `snapshot_id`를 읽고, 그 스냅샷을 Athena로 여유 구간까지 읽어 C의 `ml_ready_check` 규칙으로 판정한다. 결과(통과·위반·행 없음)와 메일 제목·본문을 돌려주면 상태 머신이 SNS로 보낸다. 위반 시 동작은 Terraform 변수 하나(`ktms_check_mode`: `observe` 기본 / `block`)로 정하고, 실행 입력 `stage=check`와 `notify=false`로 운영에 영향 없이 시험한다.

## Technical Context

**Language/Version**: Python 3.12 (Lambda 런타임, AWS SDK for pandas 관리형 레이어가 지원하는 최신). 규칙 코드는 3.11에서도 동작한다.

**Primary Dependencies**: AWS SDK for pandas 관리형 레이어(pandas, numpy, pyarrow, awswrangler), C의 `smokestack_guard.silver`(`ml_ready`, `ml_ready_check`) — 기존 `smokestack_guard.zip`을 Lambda 레이어로 재사용, `services/tms-silver/ktms_pipeline.py`(범위 계산·실행 기록)

**Storage**: 읽기 `tms_silver2.ktms_ml_ready`(Iceberg, Athena 시간 여행), `silver2/_runs/ktms_ml_ready/`. 쓰기 `silver2/_runs/ktms_ml_ready_check/`만.

**Testing**: pytest(`services/tms-silver/tests`, 루트 `tests/`). Athena·S3는 가짜 객체로 대체.

**Target Platform**: AWS Lambda(ap-northeast-2) + Step Functions Standard

**Project Type**: 데이터 파이프라인 단계(서버리스 함수 + 상태 머신 정의)

**Performance Goals**: 1회 검사 2분 이내(SC-005의 5분 안), 2일 범위 수만 행

**Constraints**: 읽기 전용(FR-012), 첫 배포는 관찰 모드(매일 스케줄이 켜져 있음), 판정 규칙 수정 금지(FR-002)

**Scale/Scope**: 하루 1회 + 수동 실행. 대상 테이블 1개(나중에 합성 1개)

## Constitution Check

| 원칙 | 판단 | 근거 |
|---|---|---|
| I. 수집 연속성 | 통과 | 수집 Lambda·스케줄·원본 경로를 건드리지 않는다. 검사 역할은 `tms_cleansys/`·`bronze/` 권한이 없다. |
| II. 비밀값 비공개 | 통과 | 비밀값 없음. 알림 이메일은 기존 토픽 구독(수집 스택)을 그대로 쓴다. |
| III. 코드로 만들고 적용은 사람이 | 통과 | Lambda·역할·상태 머신 정의 모두 Terraform(`tms-silver`). apply는 사용자. 권한 목록은 research R6. |
| IV. 데이터 계약 우선 | 통과 | 계약 판정은 C의 규칙을 그대로 쓴다. 이 기능은 계약을 바꾸지 않는다. 실행 기록 형식은 contracts/check-interface.md로 먼저 정한다. |
| V. 같은 조건의 정직한 비교 | 해당 없음(지원) | 통과 스냅샷 기록(US3)이 학습 데이터 조건을 고정하는 데 쓰인다. |
| VI. 설명 가능한 결과 | 통과 | 위반 알림에 항목·행 수·첫 행 키·스냅샷을 남긴다. |
| 운영 제약: 비용 | 통과 | Lambda 하루 1회 수십 초(무료 한도 안), Athena 스캔 수 MB(1센트 미만/일). |
| 운영 제약: 외부 패키지 | 통과 | AWS 관리형 레이어만 쓴다(이유: Lambda 기본 런타임에 pandas가 없다). |

설계 후 재점검: 위반 없음. Complexity Tracking 없음.

## Project Structure

### Documentation (this feature)

```text
specs/a-platform/010-ml-ready-contract-check/
├── spec.md
├── plan.md              # 이 파일
├── research.md          # R1~R9 결정
├── data-model.md        # 실행 입력, 검사 결과, 실행 기록
├── contracts/
│   └── check-interface.md   # 상태 머신 입력, Lambda 입출력, 실행 기록 JSON, 알림 형식
├── quickstart.md        # 운영 무영향 시험 → 관찰 → 차단 순서
└── tasks.md
```

### Source Code (repository root)

```text
services/tms-silver/
├── lambda_ktms_ml_ready_check.py   # 새 Lambda 진입점 (범위·스냅샷 → Athena 읽기 → 판정 → 기록 → 결과·메일 문안)
├── ktms_pipeline.py                # 기존. 범위 계산·창·실행 기록 함수를 재사용
└── tests/
    └── test_lambda_ktms_ml_ready_check.py

infra/stacks/tms-silver/
├── ktms_check.tf                   # 새: Lambda, 레이어(기존 패키지 zip), 역할·권한, 로그 그룹
├── ktms.tf                         # 상태 머신 템플릿 변수·역할(lambda:InvokeFunction) 추가
├── ktms_pipeline.asl.json          # Check 단계, notify·stage=check 분기, 위반·실행 실패 알림
└── variables.tf                    # ktms_check_mode, pandas_layer_arn

.github/workflows/tms-silver.yml    # 루트 tests/ 실행 단계 추가 (FR-020)
specs/a-platform/008-ktms-silver-pipeline/contracts/ktms-tables.md  # E용: 통과 스냅샷 찾는 법 (FR-018)
```

**Structure Decision**: 검사는 008 파이프라인의 한 단계라 새 서비스 폴더를 만들지 않고 `services/tms-silver/`와 `infra/stacks/tms-silver/`에 둔다(진입점 이름 규칙 `glue_*`처럼 `lambda_*`). 규칙 패키지는 Glue가 쓰는 같은 zip을 레이어로 써서 판정 코드가 한 벌만 있게 한다.

## Complexity Tracking

없음.
