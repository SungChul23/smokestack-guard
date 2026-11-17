# Implementation Plan: 학습용 합성 K-TMS 데이터 AWS Bronze 적재

**Branch**: `46-a-k-tms-silverml-ready-매일-갱신-파이프라인-glue-iceberg-silver2` | **Date**: 2026-11-17 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/a-platform/011-synthetic-train-s3-ingest/spec.md`

## Summary

EventBridge Scheduler가 매 :10, :40(KST)에 Lambda `tms-synthetic-train`을 깨운다. Lambda는 B의 `synth_train` 모듈로 전날+당일 에피소드를 seed로 다시 계산해 **이번 슬롯(과 최근 180분 안의 빈 슬롯)만** 원본 버킷 `tms_synthetic_train/`에 쓴다. 쓰기는 B의 `s3_sink.write_files_s3`(데이터 → 해시 확인 → manifest → `_SUCCESS`)를 그대로 쓰고, `_SUCCESS`가 있으면 건너뛴다. 실패는 Scheduler 재시도+DLQ, Lambda 비동기 재시도 2회+실패 목적지(같은 SQS), DLQ 알람 → 운영 SNS로 잡고, 매일 06:00 점검 실행이 전날 48개 슬롯을 확인한다. 같은 Lambda가 날짜 범위 입력으로 백필한다. 하류(합성 Silver·ML-ready, 010 검사)는 C의 `read_bronze` 경로 인자가 들어온 뒤 008 상태 머신 입력 확장으로 붙인다.

## Technical Context

**Language/Version**: Python 3.12 (Lambda). B 코드는 3.11에서 개발됐고 표준 문법만 써서 3.12에서 동작한다(테스트로 확인).

**Primary Dependencies**: AWS SDK for pandas 관리형 레이어(numpy, pandas, boto3) — 010과 같은 ARN 변수 재사용. B의 `synth_train` 모듈 11개(수정 없음). PyYAML은 쓰지 않는다: Terraform이 `daily.yaml`을 `yamldecode` → `jsonencode`로 바꿔 zip에 `config/daily.json`으로 넣는다(research R3).

**Storage**: 원본 버킷 `tms_synthetic_train/`(쓰기), `tms_synthetic_train/_manifest/`(쓰기), `tms_synthetic_train/_ref_stats/<stats_version>.csv`(읽기). SQS DLQ 1개.

**Testing**: pytest(`k_tms_synthetic_train/tests/test_lambda_handler.py`), 가짜 S3. 새 워크플로 `tms-synthetic-train.yml`이 B 테스트 전체와 함께 돈다.

**Target Platform**: AWS Lambda(ap-northeast-2) + EventBridge Scheduler + SQS + CloudWatch

**Project Type**: 예약 실행 배치 함수(수집 Lambda와 같은 모양)

**Performance Goals**: 정기 실행 30초 이내(측정: 에피소드 550개 2.2초, 슬롯 48개 파일 0.2초, 슬롯당 117~136행·gz 약 2KB). 백필 하루 1분 이내.

**Constraints**: B의 생성 규칙 수정 금지(FR-005), 실측 경로 쓰기 금지(FR-017), 비밀값 없음, 참조 통계는 저장소 밖

**Scale/Scope**: 하루 48슬롯 × 정기 실행 48회 + 점검 1회. 백필 약 19일 × 48슬롯.

## Constitution Check

| 원칙 | 판단 | 근거 |
|---|---|---|
| I. 수집 연속성 | 통과 | 실측 수집 Lambda·스케줄·`tms_cleansys/`를 건드리지 않는다. 새 역할은 `tms_cleansys/`·`bronze/` 권한이 없고 코드(`writer.check_prefix`)도 거부한다. |
| II. 비밀값 비공개 | 통과 | 접속 정보는 IAM 역할. `ref_stats`(실제 굴뚝명)는 저장소에 넣지 않고 비공개 버킷 경로에만 둔다. |
| III. 코드로 만들고 적용은 사람이 | 통과 | Lambda·스케줄·SQS·알람·권한 모두 Terraform. apply와 백필 실행은 사람. 권한 목록은 research R6. |
| IV. 데이터 계약 우선 | 통과 | Bronze 모양은 B의 계약(103 contracts)을 그대로 따른다. 합성 테이블 이름·경로는 `AGENTS.md`에 먼저 적는다. 하류 테이블 형식은 실측과 같은 계약(008·010). |
| V. 같은 조건의 정직한 비교 | 통과(지원) | 출처 `ktms_synth`로 평가에서 뺄 수 있게 하고, E 안내에 외부 검증 기간을 적는다. |
| VI. 설명 가능한 결과 | 통과 | 에피소드 태그(모양, 참조 굴뚝, seed)와 meta의 생성기·통계 버전으로 어떤 합성인지 추적된다. |
| 운영 제약: 비용 | 통과 | Lambda 월 약 3,000회 × 수 초(무료 한도 안), Scheduler 무료 한도 안, SQS 거의 0, 알람 1~2개 월 $0.2. |
| 운영 제약: 외부 패키지 | 통과 | 관리형 레이어만. B의 `confluent-kafka`는 Lambda 경로에서 import하지 않는다. |

설계 후 재점검: 위반 없음.

## Project Structure

### Documentation (this feature)

```text
specs/a-platform/011-synthetic-train-s3-ingest/
├── spec.md
├── plan.md
├── research.md          # R1~R10
├── data-model.md        # 실행 입력, 결과, DLQ 메시지, 경로
├── contracts/
│   └── ingest-interface.md   # Lambda 입출력, 수동 실행·재처리·백필 명령, 알림 문안
├── quickstart.md        # 참조 통계 업로드 → 슬롯 하나 → 정기 → 백필 → 관찰
└── tasks.md
```

### Source Code (repository root)

```text
k_tms_synthetic_train/
├── lambda_handler.py              # 새 진입점(B 폴더, B·A 공동 소유). synth_train은 수정하지 않음
└── tests/test_lambda_handler.py   # 새 테스트

infra/stacks/tms-synthetic/        # 새 스택(합성 적재 전용, 업무 단위로 독립 apply)
├── backend.tf  versions.tf  variables.tf  outputs.tf
└── main.tf                        # Lambda, zip(모듈 11개 + 진입점 + daily.json), 역할, 로그 그룹,
                                   # 스케줄 2개(정기·점검), SQS DLQ, 비동기 호출 설정, 알람

.github/workflows/tms-synthetic-train.yml   # B 테스트 + 새 테스트
.github/CODEOWNERS                           # k_tms_synthetic_train/, infra/stacks/tms-synthetic/
AGENTS.md                                    # S3 경로 규칙, 저장소 구조
specs/a-platform/008-ktms-silver-pipeline/contracts/ktms-tables.md  # (US4·US5) 합성 테이블 안내
```

**Structure Decision**: 진입점은 생성 로직과 같은 B 폴더에 둬서, B가 생성기를 고치면 다음 apply 때 zip에 그대로 반영되게 한다. 인프라는 새 스택 `tms-synthetic`으로 분리한다. 실측 수집(`tms-collection`)과 정제(`tms-silver`)에 섞으면 apply 범위가 커지고 원칙 I 위험이 생긴다. 하류(US4)는 `tms-silver` 스택의 상태 머신 입력 확장으로 하며 C의 경로 인자 뒤에 진행한다.

## Phases

1. **적재(US1~US3)**: 진입점·테스트 → 스택 → apply → 슬롯 하나 → 정기 켜기 → 백필.
2. **실패 대비(US2)**: 같은 스택에 DLQ·재시도·알람·점검 스케줄. 1과 함께 배포.
3. **하류(US4, C 대기)**: 008 상태 머신 입력에 `source`(실측·합성) 추가 → Glue 인자(원본 경로, 테이블, `data_source`) 전달 → 010 검사 입력(`check_table`, `expect_source`, `real_table`) 연결, 검사 Lambda 권한에 합성 테이블 추가.
4. **문서(US5)**: `AGENTS.md`, 008 테이블 안내, E 공유.

## Complexity Tracking

없음.
