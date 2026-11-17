# Quickstart: TW CEMS Silver 클라우드 실행 검증

실행 주체:
- AI 에이전트: 로컬 테스트, `fmt`, `validate`, `plan`
- 사람(A): `apply`, AWS 실행, Athena 조회

Terraform은 PowerShell의 `terraform.exe`(1.15.8)로 실행한다.

## 0. 사전 조건

- `tms-collection` 스택이 적용되어 있다(원본 버킷 존재).
- 원본에 `bronze/tw_cems/historical/2023-11.jsonl` ~ `2026-10.jsonl`이 있다.
- 로컬 Spark 테스트용 Docker 이미지 `sg-spark:3.5`가 있다. C의 `spark_migration_checklist.md` 1장 Dockerfile로 만든다.

## 1. 로컬 테스트 (에이전트)

```bash
# 일괄 실행 명령: boto3를 mock으로 대체, Spark 불필요
cd services/tms-silver && python3 -m pytest tests/test_run_silver.py -q

# Glue 진입 스크립트의 검사 로직: 로컬 Spark 3.5.4
docker run --rm -v "$PWD:/work" -w /work -e PYTHONPATH=/work/src:/work/services/tms-silver -e HOME=/tmp sg-spark:3.5 \
  python3 -m pytest services/tms-silver/tests/test_glue_tw_cems_silver.py -q -p no:cacheprovider
```

기대 결과:
- 다른 달 행이 섞인 입력은 쓰기 전에 실패하고, 출력 폴더에 기존 달이 그대로 남는다.
- 정상 입력은 그 달 파티션 하나와 실행 기록을 만든다.
- 파티션 값이 `tw_cems_spark.build()`의 결과와 같다.

## 2. 인프라 (사람)

```powershell
cd infra\stacks\tms-silver
terraform init
terraform plan    # 사용자가 실행한다. 생성 9, 변경 0, 삭제 0이어야 한다
terraform apply
```

기대 결과: 아래 리소스가 생긴다.
- Glue 역할 `tms-glue-silver`
- Job `tms-silver-tw-cems` (Glue 5.0)
- 스크립트·패키지 업로드
- DB `tms_silver`와 테이블 `tw_cems`
- 로그 그룹 `/aws-glue/tms-silver`

Silver용 새 버킷과 워크그룹은 만들지 않는다. 원본 버킷의 `ops/glue-scripts/`, `ops/glue-packages/`에 파일만 올라간다. 원본 버킷 설정과 `tms-collection`·`tms-eda` 리소스는 바뀌지 않는다(plan의 변경 대상에 없어야 한다).

## 3. 한 달 시험 실행 (사람)

```bash
cd services/tms-silver
python run_silver.py --from 2025-10 --to 2025-10 --dry-run
python run_silver.py --from 2025-10 --to 2025-10
```

기대 결과:
- `SUCCEEDED`
- 실행 기록 `silver/_runs/tw_cems/2025-10.json`이 있다.
- `silver_rows`가 `status_rows`의 합과 같다.
- `versions.pandas`가 기록된다(import 확인용. 버전은 결과와 무관, [research.md](research.md) R1).
- 실측 소요 시간과 비용으로 R9 추정을 고친다.

## 4. 36개월 실행 (사람)

```bash
python run_silver.py --dry-run           # 36개월 RUN, 원본에 없는 월 0
python run_silver.py --only-missing      # 2025-10은 SKIPPED
```

기대 결과: 36개월 모두 `SUCCEEDED`. 결과 표의 `silver_rows` 합계가 약 8,036만이다(SC-002).

## 5. 조회 확인 (사람, Athena 워크그룹 `tms-eda`)

```sql
-- 월별 행 수와 ok 비율. 36행이 나오고, 합계가 실행 기록과 같아야 한다
SELECT year, month, count(*) AS n, count_if(status = 'ok') AS ok
FROM tms_silver.tw_cems
GROUP BY 1, 2
ORDER BY 1, 2;

-- 파티션 조건: 읽은 양이 전체의 약 1/36이어야 한다 (SC-003)
SELECT status, count(*) FROM tms_silver.tw_cems WHERE year = '2025' AND month = '10' GROUP BY 1;

-- 전체 합계: 약 8,036만 (SC-002)
SELECT count(*) AS n FROM tms_silver.tw_cems;

-- 타입 확인: data-model.md §2와 같아야 한다
SHOW CREATE TABLE tms_silver.tw_cems;
```

실행 기록 합계와 비교한다. 아래 명령은 `jq`가 필요하다.

```bash
mkdir -p runs && aws s3 cp s3://smokestack-tms-raw-952900391026/silver/_runs/tw_cems/ runs/ --recursive
jq -s 'map(.silver_rows) | add' runs/*.json                                        # 전체 합계
jq -r '[.month, .silver_rows] | @tsv' runs/*.json                                 # 월별, 위 첫 쿼리와 비교
```

합계가 다르면 월별 표를 나란히 놓고 다른 월을 찾는다. 그 월만 `run_silver.py --from M --to M`으로 다시 실행한다.

## 6. 재실행 확인 (사람, SC-004)

```bash
python run_silver.py --from 2025-10 --to 2025-10
```

기대 결과:
- 2025-10의 행 수와 `status`별 건수가 처음 실행과 같다.
- 다른 월의 건수는 바뀌지 않는다(5의 첫 쿼리를 다시 실행해 비교).

## 7. 원본 무변경 확인 (사람, SC-005)

```bash
aws s3 ls s3://smokestack-tms-raw-952900391026/bronze/tw_cems/historical/ --summarize
```

실행 전후로 `bronze/` 아래 객체 수와 크기 합계가 같아야 한다. `tms_cleansys/`는 수집이 계속 진행되므로 비교 대상이 아니다.

## 8. 권한 확인 (사람, SC-005·US3)

`<ROLE_ARN>`은 `terraform output -raw glue_role_arn`의 값이다.

```bash
R=arn:aws:s3:::smokestack-tms-raw-952900391026
aws iam simulate-principal-policy --policy-source-arn <ROLE_ARN> \
  --action-names s3:PutObject s3:DeleteObject \
  --resource-arns $R/bronze/tw_cems/historical/2025-10.jsonl $R/tms_cleansys/_state/latest.json \
                  $R/silver/tw_cems/year=2025/month=10/x.parquet $R/silver/tw_cems_ml_ready/x \
  --query 'EvaluationResults[].[EvalActionName,EvalResourceName,EvalDecision]' --output table

aws iam simulate-principal-policy --policy-source-arn <ROLE_ARN> \
  --action-names s3:ListBucket --resource-arns $R \
  --context-entries ContextKeyName=s3:prefix,ContextKeyValues=tms_cleansys/,ContextKeyType=string \
  --query 'EvaluationResults[].EvalDecision' --output text
```

기대 결과:

| 동작 | 대상 | 결과 |
|---|---|---|
| Put / Delete | `bronze/tw_cems/...` | `implicitDeny` |
| Put / Delete | `tms_cleansys/...` | `implicitDeny` |
| Put / Delete | `silver/tw_cems/...` | `allowed` |
| Put / Delete | `silver/tw_cems_ml_ready/...` | `implicitDeny` |
| ListBucket | prefix `tms_cleansys/` | `implicitDeny` |
