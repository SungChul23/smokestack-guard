# Tasks: 합성 데이터 v2 전환·재수집과 학습 스냅샷 알림

**Input**: `specs/a-platform/015-synthetic-v2-snapshot-notice/` (spec, plan, research, data-model, contracts/notice-format.md, quickstart)

**표시**: [P] 다른 파일이라 같이 해도 됨 · [US1]~[US3] spec의 사용자 스토리 · 🧑 사람(A)이 AWS에서 · 📨 다른 담당과 공유

## Phase 1: Setup

- [X] T001 PR #72(B의 v2 생성기) 머지 확인, 브랜치에 포함 (`git merge-base --is-ancestor 0ab1379 HEAD`).
- [ ] T002 🧑 참조 통계를 `tms_synthetic_train_v2/_ref_stats/ref-1030-1110.csv`로 복사 (quickstart §1, research R2).

## Phase 2: US1 - v2 적재 (P1) 🎯

**목표**: 30분 적재가 v2 경로에만 쓴다. **독립 확인**: quickstart §2.

- [X] T003 [P] [US1] `k_tms_synthetic_train/tests/test_lambda_handler.py`: manifest 경로를 `lh.MANIFEST_PREFIX`로(v1 하드코딩 제거), v2 경로에 쓰는지·v1 경로에 안 쓰는지 단언 추가.
- [X] T004 [US1] `infra/stacks/tms-synthetic/main.tf`: `local.root = "tms_synthetic_train_v2"`, 머리 주석·역할·함수 설명의 경로; `variables.tf` 설명. zip 모듈 목록은 그대로(진입점이 `real_events` 안 씀, R1).
- [X] T005 [P] [US1] `k_tms_synthetic_train/README.md` AWS 적재 절: 경로 v2, v1 보존.
- [X] T006 [US1] 합성 테스트 전체(`python -m pytest -q`), `terraform fmt`·`validate`.

## Phase 3: US2 - Silver 원본 v2 (P1)

**목표**: 합성 Silver가 v2 원본을 읽는다. **독립 확인**: quickstart §5·§6.

- [X] T007 [US2] `infra/stacks/tms-silver/ktms_synth.tf`: `synth_source_prefix = "tms_synthetic_train_v2"`, 머리 주석.
- [X] T008 [US2] `infra/stacks/tms-silver/ktms_pipeline.asl.json`: 합성 `source_prefix` → `tms_synthetic_train_v2/`, 주석.
- [X] T009 [P] [US2] `services/tms-silver/tests/test_ktms_asl.py`·`test_glue_ktms_silver.py`·`test_ktms_pipeline.py`: 합성 경로 문자열 v2.
- [X] T010 [P] [US2] `AGENTS.md` S3 경로 규칙: `tms_synthetic_train_v2/`(합성 적재 Lambda만 씀) 추가, `tms_synthetic_train/`은 v1 보존만.

## Phase 4: US3 - 학습 스냅샷 알림 (P2)

**목표**: 매일 05:00 메일. **독립 확인**: quickstart §7.

- [X] T011 [P] [US3] `services/tms-silver/tests/test_training_notice.py`: 가짜 S3 기록으로 — 출처별 최근 통과 3개(날짜별 최신 하나), 실패·없음 표시, Silver 짝(ML-ready 시작 전 마지막 성공 Silver), 확정 범위 첫날~실행일−2, 본문에 읽기 예시, 7일 통과분 없음 문구, `dry_run`이면 발행 안 함, 코드에 `@` 이메일 없음.
- [X] T012 [US3] `services/tms-silver/lambda_training_snapshot_notice.py`: 기록 목록(7일, `StartAfter`)·읽기, 고르기, 본문(contracts/notice-format.md), `TOPIC_ARN`에 발행, 응답 JSON. 표준 라이브러리 + boto3.
- [X] T013 [US3] `infra/stacks/tms-silver/training_notice.tf`: SNS 토픽 `tms-training-snapshots`, 이메일 구독(SSM `/tms/notice/training-snapshot-emails` 목록, 2026-11-20 TF_VAR에서 변경), Lambda(zip: 알림 파일 하나) + 로그 그룹 14일, 역할(`silver2/_runs/*` 목록·읽기, 토픽 발행), Scheduler `cron(0 5 * * ? *)` Asia/Seoul + 역할, 스위치 `training_notice_enabled`.
- [X] T014 [US3] `infra/stacks/tms-silver/variables.tf`: `training_notice_emails_param`(SSM 이름), `training_notice_enabled`(bool, 기본 true); `outputs.tf`에 토픽 ARN.
- [X] T015 [US3] tms-silver 테스트·ruff, `terraform fmt`·`validate`.

## Phase 5: 적용·확인 (사람)

- [ ] T016 🧑 `tms-synthetic` plan·apply(Lambda 코드·역할 정책·설명만) → 다음 슬롯이 v2 경로에 생기는지(SC-001).
- [ ] T017 🧑 다시 채우기 7일씩 4번 + `check` 몇 날짜(SC-002).
- [ ] T018 🧑 `tms-silver` SSM 수신 주소 등록 → plan·apply → 구독 확인 메일 📨 E.
- [ ] T019 🧑 `run_ktms.py backfill --source synth --from 2026-10-30 --to <D−2>` → 계약 검사 → Athena `OTHER` 0개·모양 분포(SC-003).
- [ ] T020 🧑 알림 `dry_run` → 실제 발행 → 다음 날 05:00 메일(SC-004).
- [ ] T021 📨 E에게 전환 공지(v2 변화, 첫 v2 스냅샷, v1은 시간 여행으로 남음), B·C에 경로 변경 공유.

## Phase 6: Polish

- [ ] T022 spec Status 갱신, 이슈 #73 체크.

## Dependencies

- T002는 T016 전에. T004(적재 경로)와 T007·T008(Silver 경로)은 같은 PR에, apply는 T016 → T017 → T018 → T019 순서(research R8).
- US3(T011~T015)은 US1·US2와 독립(실측 기록만으로도 동작).

## Parallel Example

```
T003 | T005 | T009 | T010 | T011
```
