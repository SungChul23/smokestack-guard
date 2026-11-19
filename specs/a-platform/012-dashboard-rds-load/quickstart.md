# Quickstart: 대시보드 관측 적재 확인

모든 `terraform`·AWS·DB 명령은 사람이 실행한다(AGENTS.md).

## 1. 사전 조건

- 009 서비스 인프라: `tms-network`·`tms-database` 적용됨
- 운영 SNS 토픽 `tms-collector-alerts` 있음
- D의 사업장 목록을 원본 버킷 `ref/sites/<버전>.csv`에 올림(contracts §4 컬럼)

## 2. 인프라 적용 (PowerShell)

```powershell
cd infra/stacks/tms-network;        terraform plan; terraform apply   # 보안그룹 tms-loader, DB 5432 규칙 추가만
cd ../tms-database; $env:TF_VAR_rds_enabled="true"; terraform plan; terraform apply   # IAM DB 인증 켜기 (+ RDS·베스천 켜짐)
cd ../tms-dashboard-load;           terraform init; terraform plan; terraform apply   # 스케줄은 꺼진 채 생성
```

- `tms-network` plan은 추가만이어야 한다(기존 규칙 변경·삭제 없음).
- `tms-database` plan에서 RDS가 **교체(replace)되지 않고 수정(update in-place)**인지 확인한다.

## 3. DB 구조 만들기

```bash
# 터널 (다른 창): ssh -i tms-bastion.pem -L 5433:<db_host>:5432 ec2-user@bastion.smokestack-guard.store
cd services/dashboard-load
python run_dashboard_load.py migrate --dry-run     # 적용할 파일 목록
python run_dashboard_load.py migrate
python run_dashboard_load.py load-ref --sites s3://smokestack-tms-raw-952900391026/ref/sites/<버전>.csv
```

확인: `ref.site` 행 수가 사업장 목록과 같다(약 909). `ref.status_code` 9행.

## 4. 한 번 실행해 보기 (US1)

```bash
aws stepfunctions start-execution --state-machine-arn <tms-dashboard-load ARN> --input '{"mode":"recent"}'
```

- 실행 결과 `rows.upserted` > 0, `measured_range.max`가 가장 최근 확정 슬롯
- 같은 입력을 한 번 더 → `rows.upserted` = 0, `unchanged` = 앞의 `read`(SC-002)
- `SELECT count(*) FROM obs.measurement_30m WHERE status_code <> 0 AND value IS NOT NULL;` → 0 (SC-005)

## 5. 다시 채우기 (US4)

```bash
python run_dashboard_load.py backfill --from 2026-10-30 --to <오늘> --dry-run
python run_dashboard_load.py backfill --from 2026-10-30 --to <오늘>
```

- 날짜별 행 수 표가 나온다. 1시간 안에 끝난다(SC-006).
- 한 번 더 실행해도 표가 같다.

## 6. Silver와 일치 확인 (SC-003)

확정된 날짜(D−2 이전)를 골라 Athena(`tms_silver2`)와 RDS에서 날짜·물질별 행 수와 값 합계를 구해 비교한다. 다르면 그 날짜에 빠진 실행이 있었던 것이니 `backfill --from <날짜> --to <날짜>`로 고친다.

```sql
-- Athena
SELECT date(ts_kst) d, item, count(*) n, sum(value) sv, count_if(status <> 'ok') ns
FROM tms_silver2.ktms
WHERE item IN ('nox','sox') AND ts_kst >= TIMESTAMP '2026-11-17 00:00:00' AND ts_kst < TIMESTAMP '2026-11-19 00:00:00'
GROUP BY 1, 2 ORDER BY 1, 2;
```
```sql
-- RDS
SELECT measured_at::date d, item, count(*) n, sum(value) sv, count(*) FILTER (WHERE status_code <> 0) ns
FROM obs.measurement_30m
WHERE measured_at >= '2026-11-17' AND measured_at < '2026-11-19'
GROUP BY 1, 2 ORDER BY 1, 2;
```

## 7. 스케줄 켜기

```powershell
cd infra/stacks/tms-dashboard-load; terraform apply   # 2026-11-19부터 기본값 true. 처음부터 다시 만들 때는 $env:TF_VAR_load_schedule_enabled="false"로 꺼 둔 채 §3~§6을 먼저 한다
```

- 다음 :15·:45 실행이 성공하는지, 다음 날 03:20 `daily`가 `summary_days`(최근 2일 이상)를 돌려주고 관측 행 수는 바꾸지 않는지 확인한다.

## 8. RDS를 끄면

```powershell
cd infra/stacks/tms-database; $env:TF_VAR_rds_enabled="false"; terraform apply
```

- 다음 실행이 `{"skipped":"rds_off"}`로 성공하고 메일이 오지 않는다(FR-006·011).
- 다시 켤 때는 스냅샷 복원 또는 §3·§5를 다시 한다.

## 9. 앱 계정 확인 (US5)

`tms_app`으로 접속해 `INSERT INTO obs.measurement_30m …` → 권한 오류, `INSERT INTO app.user_favorite …` → 성공(SC-008).
