# Contract: 계약 검사 단계 입출력

## 1. 수동 실행 (운영자)

```bash
# 검사만, 알림 없음 (운영 무영향 시험)
aws stepfunctions start-execution --region ap-northeast-2 \
  --state-machine-arn arn:aws:states:ap-northeast-2:952900391026:stateMachine:tms-silver2-ktms \
  --input '{"stage":"check","start_date":"2026-11-15","end_date":"2026-11-16","notify":false}'

# 검사만, 알림까지 (알림 문안 확인)
  --input '{"stage":"check","notify":true}'
```

- `stage=check`는 Glue 잡을 실행하지 않는다. 테이블에 쓰지 않는다.
- 날짜를 주면 그 범위, 안 주면 auto(끝난 최근 2일).

## 2. Lambda 입력 (상태 머신 → Lambda)

```json
{
  "args": {"start_date": "auto", "end_date": "auto", "stage": "all", "notify": true,
           "check_table": "tms_silver2.ktms_ml_ready", "expect_source": null, "real_table": null},
  "ml_ready_job_run_id": "jr_…",          // stage=check면 null
  "sfn_execution": "…",
  "mode": "observe"
}
```

## 3. Lambda 출력

```json
{"result": "violation", "table": "tms_silver2.ktms_ml_ready",
 "range": {"start": "2026-11-15", "end": "2026-11-16"}, "snapshot_id": 1234567890,
 "rows": 41234, "violations": 3,
 "run_record": "s3://smokestack-tms-raw-952900391026/silver2/_runs/ktms_ml_ready_check/20261117T030912Z_<id>.json",
 "subject": "[tms] K-TMS contract violation - ktms_ml_ready 2026-11-15~2026-11-16 (3)",
 "message": "…"}
```

## 4. 알림 본문

### 위반

```
K-TMS ML-ready 계약 위반 (3건)

테이블: tms_silver2.ktms_ml_ready
범위: 2026-11-15 ~ 2026-11-16 (41,234행)
스냅샷: 1234567890
모드: observe (실행은 성공 처리, 데이터는 이미 커밋됨)

[재계산] 재계산 불일치 label_entry_60m: 12행 (첫 행 ['A|F|1', 'nox', '2026-11-15 09:30:00'])
[규칙] headroom_pct != 90 − ratio_pct: 2행
[형식] 키 중복 4행
… 외 0건

전체 목록: s3://…/silver2/_runs/ktms_ml_ready_check/<…>.json
검사만 다시: aws stepfunctions start-execution … --input '{"stage":"check","start_date":"2026-11-15","end_date":"2026-11-16"}'
학습: 이 스냅샷 대신 마지막 통과 스냅샷을 쓴다 (008 contracts/ktms-tables.md)
읽는 법: specs/a-platform/010-ml-ready-contract-check/contracts/check-interface.md
실행 이름: <sfn_execution>
```

- 항목은 `[형식]`·`[규칙]`·`[재계산]`·`[겹침]` 순, 최대 10줄.

### 대상 행 없음

```
K-TMS ML-ready 계약 검사: 대상 범위에 행이 없다
범위·스냅샷·실행 이름 + "수집 공백은 누락률 리포트를 확인한다"
```

### 검사 실행 실패 (상태 머신이 작성)

```
K-TMS ML-ready 계약 검사 실행 실패 (재시도 1회 후)
범위: <start> ~ <end>
오류 종류: <Error>
원인: <Cause 원문>
로그: CloudWatch /aws/lambda/tms-ktms-ml-ready-check
실행 이름: <sfn_execution>
모드: <observe|block>
```

## 5. 실행 기록

data-model.md §4. JSON, UTF-8, 들여쓰기 2.
