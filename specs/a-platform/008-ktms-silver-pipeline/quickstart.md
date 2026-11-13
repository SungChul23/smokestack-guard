# Quickstart: K-TMS Silver·ML-ready 파이프라인 검증

AWS 실행 명령과 `terraform plan/apply`는 사람이 실행한다(AGENTS.md). Athena 쿼리는 콘솔의 워크그룹 `tms-eda`에서 실행한다.

## 0. 로컬 테스트

```bash
cd services/tms-silver
. .venv/bin/activate && pip install -e ".[dev]"
ruff check .
pytest -q                     # 단위 + Iceberg 통합(처음 한 번 Maven에서 jar를 받는다)
pytest -q -m "not iceberg"    # 네트워크 없이 단위 테스트만
```

기대 결과: 모두 통과. 특히 다음 둘을 본다.
- `test_ml_ready_context_equivalence`: 앞뒤 범위만으로 계산한 결과가 전체 계산과 35컬럼 모두 같다.
- `test_overwrite_range_keeps_other_days`: 범위 밖 날짜가 바뀌지 않는다.

## 1. 배포 (PowerShell)

```powershell
cd infra/stacks/tms-silver
terraform plan    # 추가 리소스: Glue 잡 2, IAM 역할 4(Glue 2, Step Functions, Scheduler), 상태 머신 1, 스케줄 1, S3 객체(스크립트), 로그 그룹
terraform apply
```

- 스케줄은 `state = "DISABLED"`로 만든다. 3단계(전체 생성)가 끝난 뒤 변수 `ktms_schedule_enabled = true`로 켠다.

## 2. 첫 실행: 하루치 시험 (US1)

```bash
cd services/tms-silver
python run_ktms.py rerun --from 2026-11-11 --to 2026-11-11 --dry-run
python run_ktms.py rerun --from 2026-11-11 --to 2026-11-11
python run_ktms.py runs --table ktms --last 1
python run_ktms.py runs --table ktms_ml_ready --last 1
```

확인할 것:
- 실행 기록의 `versions.pandas`가 `missing`이 아니다.
- 로그에 `AccessDenied`가 없다.
- `rows_per_day`에 11-11 하나만 있다.
- 실행 시간과 driver 메모리(Glue 콘솔 지표)를 본다. 메모리가 부족해 보이면 `--max_days`와 묶음 크기를 줄인다.

## 3. 처음 전체 생성 (US2)

```bash
python run_ktms.py backfill --from 2026-10-30 --to <어제 KST> --dry-run
python run_ktms.py backfill --from 2026-10-30 --to <어제 KST>
```

### SC-001: Silver가 C의 로컬 결과와 같다

```sql
SELECT count(*) AS rows FROM tms_silver2.ktms
WHERE ts_kst >= TIMESTAMP '2026-10-31 00:00:00' AND ts_kst < TIMESTAMP '2026-11-11 00:00:00';
-- 기대: 3,304,429 (PR #45)

SELECT status, count(*) FROM tms_silver2.ktms
WHERE ts_kst >= TIMESTAMP '2026-10-31 00:00:00' AND ts_kst < TIMESTAMP '2026-11-11 00:00:00'
GROUP BY status ORDER BY 2 DESC;
```

- 행 수가 다르면 날짜별 행 수(`rows_per_day`)를 C의 로컬 출력과 비교해 어느 날이 다른지 찾는다.
- `status` 분포는 거의 같아야 한다. 차이는 C의 실행 뒤에 들어온 정정(`checking → stopped`) 몇 건 정도만 허용된다.
- 값까지 비교하려면 C가 같은 범위로 로컬 `build`를 돌려 만든 Parquet과 Athena 결과를 키 기준으로 비교한다(C에게 요청).

### SC-002: ML-ready가 C의 로컬 결과와 같다

```sql
SELECT count_if(classification_eligible) AS eligible,
       count_if(classification_eligible AND label_entry_60m = 1) AS positives
FROM tms_silver2.ktms_ml_ready
WHERE measured_at >= TIMESTAMP '2026-10-31 00:00:00' AND measured_at < TIMESTAMP '2026-11-11 00:00:00';
-- 기대: eligible 956,194 / positives 3,768 (PR #45)
```

컬럼 이름·순서가 `tw_cems_ml_ready`와 같은지 본다.

```sql
SELECT column_name, ordinal_position FROM information_schema.columns
WHERE table_schema = 'tms_silver2' AND table_name IN ('ktms_ml_ready', 'tw_cems_ml_ready')
ORDER BY table_name, ordinal_position;
```

## 4. 다시 실행해도 같다 (SC-004)

```sql
SELECT snapshot_id, committed_at FROM "tms_silver2"."ktms$snapshots" ORDER BY committed_at DESC LIMIT 2;
```

같은 범위로 한 번 더 실행한다(`rerun --from 2026-11-05 --to 2026-11-05`). 그다음 이전 버전과 최신 버전의 차이를 본다.

```sql
SELECT count(*) FROM (
  (SELECT * FROM tms_silver2.ktms FOR VERSION AS OF <이전 snapshot_id> WHERE ts_kst >= TIMESTAMP '2026-11-05 00:00:00' AND ts_kst < TIMESTAMP '2026-11-06 00:00:00')
  EXCEPT
  (SELECT * FROM tms_silver2.ktms WHERE ts_kst >= TIMESTAMP '2026-11-05 00:00:00' AND ts_kst < TIMESTAMP '2026-11-06 00:00:00')
);
-- 기대: 0 (양쪽 방향 모두)
```

## 5. 버전 고정 (SC-005, US3)

3단계가 끝난 직후 `ktms_ml_ready`의 최신 `snapshot_id`와 행 수를 적어 둔다. 매일 실행이 3번 돈 뒤 다음을 실행한다.

```sql
SELECT count(*), sum(label_ratio_60m) FROM tms_silver2.ktms_ml_ready FOR VERSION AS OF <적어 둔 id>;
-- 기대: 적어 둔 값과 같음
```

## 6. 실패 알림 (SC-006, US4)

데이터가 없는 미래 범위가 아니라 원본이 없는 과거 범위로 실행한다. 잡이 날짜 검사를 통과해야 하기 때문이다.

```bash
python run_ktms.py rerun --from 2026-10-01 --to 2026-10-01
```

기대 결과:
- Silver 단계가 "원본 스냅샷 0개"로 실패하고 1회 재시도 뒤에도 실패한다.
- 10분 안에 `[tms] K-TMS silver2 failed` 메일이 온다.
- ML-ready는 실행되지 않는다.
- 두 테이블의 최신 `snapshot_id`가 바뀌지 않는다.
- `silver2/_runs/ktms/`에 `result: failed` 기록이 2개(첫 시도와 재시도) 생긴다.

## 7. 매일 실행 켜기 (US1, SC-003)

```powershell
# variables.tf의 기본값을 true로 바꿔 커밋한 뒤 apply한다(2026-11-13).
# 환경 변수로 켜면 다음에 환경 변수 없이 apply할 때 다시 꺼진다.
terraform apply
```

- 다음 날 아침 실행 기록과 `$snapshots`에 새 버전이 생겼는지 본다.
- 7일 연속 성공하면 SC-003을 충족한다.

## 8. 원본 쓰기 0 (SC-007)

배포 전과 7일 운영 뒤에 같은 수집일 범위(예: 2026-11-01 ~ 11-10)의 객체 수와 크기를 비교한다.

```bash
for d in 2026-11-01 2026-11-05 2026-11-10; do
  aws s3 ls s3://smokestack-tms-raw-952900391026/tms_cleansys/ingest_date=$d/ --recursive --summarize | tail -2
done
```

IAM 정책에 `tms_cleansys/*` 쓰기·삭제 권한이 없는지도 정책 문서로 확인한다(plan의 권한 표).
