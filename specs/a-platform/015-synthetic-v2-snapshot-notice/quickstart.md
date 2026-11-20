# Quickstart: 합성 v2 전환 → 다시 채우기 → Silver 다시 계산 → 알림

모든 AWS 명령·Terraform은 A가 실행한다. 같은 날 순서대로 한다(R8).

## 1. 참조 통계 복사 🖥️

```bash
B=smokestack-tms-raw-952900391026
aws s3 cp s3://$B/tms_synthetic_train/_ref_stats/ref-1030-1110.csv s3://$B/tms_synthetic_train_v2/_ref_stats/ref-1030-1110.csv
```

## 2. 합성 적재 v2 🪟

```powershell
cd infra/stacks/tms-synthetic; terraform plan   # Lambda 코드·역할 정책(v2 경로)·설명만 수정
terraform apply
```
다음 :10 또는 :40 뒤 확인:
```bash
aws s3 ls s3://$B/tms_synthetic_train_v2/ --recursive | tail -4      # snapshot·meta·manifest·_SUCCESS
```

## 3. 다시 채우기 (7일씩) 🖥️

```bash
for r in "2026-10-30 2026-11-05" "2026-11-06 2026-11-12" "2026-11-13 2026-11-19" "2026-11-20 <오늘>"; do
  set -- $r
  aws lambda invoke --function-name tms-synthetic-train --cli-binary-format raw-in-base64-out \
    --payload "{\"mode\":\"backfill\",\"from\":\"$1\",\"to\":\"$2\"}" /dev/stdout
done
aws lambda invoke --function-name tms-synthetic-train --cli-binary-format raw-in-base64-out --payload '{"mode":"check","day":"2026-11-05"}' /dev/stdout
```

## 4. Silver 원본 경로·알림 🪟

먼저 수신 주소를 SSM에 한 번 등록한다(주소는 저장소에 쓰지 않음, 바꿀 때도 이 값만 고치고 apply).
```bash
aws ssm put-parameter --name /tms/notice/training-snapshot-emails --type StringList --value "<주소1>,<주소2>"
```

```powershell
cd infra/stacks/tms-silver
terraform plan    # 합성 잡 인자·역할(v2 경로), 상태 머신 정의, 알림 Lambda·토픽·구독·스케줄
terraform apply
```
받는 사람에게 "AWS Notification - Subscription Confirmation" 메일의 확인 링크를 눌러 달라고 한다.

## 5. Silver 다시 계산 🖥️

```bash
cd services/tms-silver
python run_ktms.py backfill --source synth --from 2026-10-30 --to <D−2> --dry-run
python run_ktms.py backfill --source synth --from 2026-10-30 --to <D−2>
```
끝나면 계약 검사(011 quickstart와 같음).

## 6. 확인 (Athena)

```sql
-- v1 모양이 없는지 (0이어야 함)
SELECT count(DISTINCT stack_code) FROM tms_silver2.ktms_synth_ml_ready WHERE stack_code LIKE '%-OTHER-%';
-- v2 모양 분포
SELECT regexp_extract(stack_code, '^SYN-T-\d{8}-(NOX|SOX)-([A-Z_]+)-', 2) AS shape, count(DISTINCT stack_code)
FROM tms_silver2.ktms_synth_ml_ready GROUP BY 1 ORDER BY 2 DESC;
```

## 7. 알림 시험 🖥️

```bash
aws lambda invoke --function-name tms-training-snapshot-notice --cli-binary-format raw-in-base64-out \
  --payload '{"dry_run": true}' /dev/stdout     # 본문만
aws lambda invoke --function-name tms-training-snapshot-notice --payload '{}' /dev/stdout   # 실제 발행
```
다음 날 05:00 메일이 오는지 본다(SC-004).

## 8. E에게 공지

전환 날짜, v2 변화(모양 10종, 양 1:1), 첫 v2 스냅샷 ID(메일), v1 스냅샷은 시간 여행으로 남음.
