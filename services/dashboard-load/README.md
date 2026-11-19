# dashboard-load

대시보드·에이전트가 읽을 K-TMS 관측(NOx·SOx, 30분)을 RDS에 채운다. 설계: [specs/a-platform/012-dashboard-rds-load](../../specs/a-platform/012-dashboard-rds-load/spec.md)

- 정본은 S3 Silver다. RDS는 언제든 다시 만들 수 있는 서비스용 복사본이다.
- 원본 → C의 `read_bronze`·`to_silver`(수정 없이) → 굴뚝 키·상태 번호 → `obs.measurement_30m` UPSERT.
- 측정값이 없는 칸은 `value` null + `status_code`. 0으로 채우지 않는다.

| 파일 | 하는 일 |
|---|---|
| `lambda_handler.py` | Lambda 진입점. `mode` = `recent`(30분) · `daily`(요약·매핑 점검) · `day`(하루 다시 채우기) |
| `load.py` | 원본 범위, C의 규칙 호출, 적재용 정리 (DB 없이 테스트) |
| `db.py` | IAM 토큰 접속, UPSERT, 일일 요약·매핑 점검 SQL, 마이그레이션, 사업장 목록 적재 |
| `run_dashboard_load.py` | 사람 명령: `migrate` · `load-ref` · `backfill` · `status` |
| `migrations/*.sql` | 스키마 `ref`·`obs`·`ops`·`app`·`rag`, 계정 `tms_loader`·`tms_app` |
| `certs/global-bundle.pem` | RDS 공용 CA 번들 (공개 인증서, https://truststore.pki.rds.amazonaws.com/global/global-bundle.pem) |
| `build_layer.sh` | pg8000 레이어 zip (`terraform plan` 전에 실행) |

## 접속

- 적재 Lambda: `tms_loader`, RDS IAM 인증(비밀번호 없음). VPC 앱 서브넷, NAT 없이 S3 게이트웨이 엔드포인트만.
- 사람(`migrate`·`load-ref`·`status`): 베스천 터널로 `tms_admin`. 비밀번호는 실행 시 Secrets Manager에서 읽는다.
  ```bash
  ssh -i tms-bastion.pem -L 5433:<db_host>:5432 ec2-user@bastion.smokestack-guard.store
  python run_dashboard_load.py migrate --dry-run
  ```
- D 앱: `tms_app`, IAM 인증. `ref`·`obs` 읽기, `app`·`rag` 쓰기.

## 테스트

```bash
python3.11 -m venv .venv && .venv/bin/pip install "pandas>=2.2" numpy boto3 "pg8000==1.31.2" "scramp==1.4.6" pytest ruff
docker run -d --name tms-pg-test -e POSTGRES_PASSWORD=test -p 55432:5432 pgvector/pgvector:pg16
TEST_PG_PASSWORD=test .venv/bin/python -m pytest -q    # TEST_PG_PASSWORD가 없으면 DB 테스트는 건너뜀
.venv/bin/ruff check .
```
