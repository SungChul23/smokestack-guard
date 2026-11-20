# Implementation Plan: 합성 데이터 v2 전환·재수집과 학습 스냅샷 알림

**Branch**: `73-a-합성-데이터-v2-전환재수집1030silver-재계산학습-스냅샷-알림` | **Date**: 2026-11-20 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/a-platform/015-synthetic-v2-snapshot-notice/spec.md`

## Summary

B의 v2 생성기(PR #72, 머지됨)를 쓰도록 합성 적재 Lambda의 zip과 쓰기 권한을 v2 경로(`tms_synthetic_train_v2/`)로 바꾸고, 10/30부터 다시 채운 뒤, Silver 합성 잡의 원본 경로를 v2로 바꿔 같은 표(`ktms_synth`, `ktms_synth_ml_ready`)를 10/30~D−2로 다시 계산한다. v1 원본과 이전 스냅샷은 남긴다. 새 Lambda가 매일 05:00 KST에 실행 기록에서 실측·합성의 계약 검사 통과 스냅샷(Silver·ML-ready)과 확정 범위를 모아 SNS로 E에게 메일을 보낸다. 수신 주소는 TF_VAR로만 넣는다.

## Technical Context

**Language/Version**: Python 3.12(Lambda), 3.11+(명령) · Terraform `~> 1.15.0`, AWS provider `~> 6.0`

**Primary Dependencies**: B의 `synth_train`(v2, 수정 없이), 표준 라이브러리 + boto3(알림 Lambda). 새 패키지 없음

**Storage**: 원본 버킷 `tms_synthetic_train_v2/`(새로), Silver 합성 Iceberg 표(같은 이름, 새 스냅샷), 실행 기록 `silver2/_runs/…`(읽기만)

**Testing**: pytest — 합성 진입점 v2 경로, Silver 합성 경로·상태 머신 정의, 알림(기록 고르기·Silver 짝 찾기·실패·없음·본문·이메일이 코드에 없음)

**Target Platform**: Lambda, Glue(기존), Step Functions(기존), EventBridge Scheduler, SNS

**Performance Goals**: 다시 채우기 7일 묶음 900초 안, Silver 다시 계산은 008 backfill과 같은 규모, 알림 Lambda 수 초

**Constraints**: v1 원본·스냅샷 삭제 없음. 실측 수집·실측 Silver·대시보드 적재 변경 없음. 개인 이메일 저장소 금지

**Scale/Scope**: 합성 23일 × 48슬롯, v2 하루 에피소드 약 158

## Constitution Check

| 원칙 | 판정 | 근거 |
|---|---|---|
| I. 수집 연속성 | 통과 | 실측 수집(`tms_cleansys/`)·스케줄을 건드리지 않는다. 합성 원본은 새 경로에 쓰고 v1을 지우지 않는다 |
| II. 비밀값 비공개 | 통과 | 비밀 없음. 참조 통계(실제 굴뚝명)는 사람이 S3에서 복사. 수신 이메일은 TF_VAR로만 |
| III. 코드로 만들고 적용은 사람이 | 통과 | 자원·경로는 Terraform, 다시 채우기·재계산·apply는 A |
| IV. 데이터 계약 우선 | 통과 | 표 이름·열은 그대로, 모양 이름 목록과 경로 변경을 data-model·AGENTS.md에 적는다. 알림 형식은 contracts |
| V. 같은 조건의 정직한 비교 | 통과 | 합성은 Train에만(`data_source='ktms_synth'`) 메일에 명시. 실측 평가 데이터는 바뀌지 않음 |
| VI. 설명 가능한 결과 | 통과 | 알림이 스냅샷마다 실행일·검사 결과·확정 범위를 함께 보여 준다 |

### IAM 권한 (바뀌는 것만)

| 주체 | 전 | 후 |
|---|---|---|
| 합성 적재 Lambda 역할 | `tms_synthetic_train/*` 쓰기 | `tms_synthetic_train_v2/*` 쓰기 |
| 합성 Silver 잡 역할 | `tms_synthetic_train/ingest_date=*` 읽기 | `tms_synthetic_train_v2/ingest_date=*` 읽기 |
| 알림 Lambda 역할(새) | — | `s3:ListBucket`(`silver2/_runs/*`), `s3:GetObject`(`silver2/_runs/*`), `sns:Publish`(`tms-training-snapshots`), 기본 로그 |
| 알림 Scheduler 역할(새) | — | `lambda:InvokeFunction`(알림 Lambda) |

## Project Structure

### Documentation

```text
specs/a-platform/015-synthetic-v2-snapshot-notice/
├── spec.md  plan.md  research.md  data-model.md  quickstart.md
├── contracts/notice-format.md
├── checklists/requirements.md
└── tasks.md
```

### Source Code

```text
k_tms_synthetic_train/tests/test_lambda_handler.py   # v1 경로 하드코딩 → lh.MANIFEST_PREFIX
k_tms_synthetic_train/README.md                       # AWS 적재 절에 v2 경로
infra/stacks/tms-synthetic/main.tf                    # local.root = tms_synthetic_train_v2, 설명
infra/stacks/tms-synthetic/variables.tf               # 설명
infra/stacks/tms-silver/ktms_synth.tf                 # synth_source_prefix = tms_synthetic_train_v2
infra/stacks/tms-silver/ktms_pipeline.asl.json        # 합성 source_prefix
infra/stacks/tms-silver/training_notice.tf            # 새: 토픽·구독·Lambda·로그·스케줄·역할
infra/stacks/tms-silver/variables.tf                  # training_notice_emails_param(SSM 이름), training_notice_enabled
services/tms-silver/lambda_training_snapshot_notice.py  # 새: 기록 고르기·본문·발행
services/tms-silver/tests/test_training_notice.py     # 새
services/tms-silver/tests/test_ktms_asl.py, test_glue_ktms_silver.py, test_ktms_pipeline.py  # 합성 경로 문자열
AGENTS.md                                              # S3 경로 규칙: v2 추가, v1 보존만
```

**Structure Decision**: 알림은 실행 기록을 만드는 `tms-silver` 스택·폴더에 둔다(같은 버킷 경로 권한, 같은 배포 단위). 합성 적재 코드는 B의 것이라 우리 진입점 테스트만 고친다.

## Complexity Tracking

| 항목 | 필요한 이유 | 더 단순한 대안을 버린 이유 |
|---|---|---|
| 알림 전용 예약 Lambda | 실측·합성을 한 통으로, 상태 머신 무변경 | 상태 머신 끝 단계는 출처마다 두 통·정의 변경 큼 |
| Silver 스냅샷을 "ML-ready 시작 전 마지막 성공 Silver"로 짝짓기 | 손으로 다시 계산한 실행에도 맞음 | `sfn_execution` 같기 비교는 수동 실행(`manual`)에서 못 씀 |
