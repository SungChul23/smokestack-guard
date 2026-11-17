# tms-missing-rate

전날(한국 시각) Bronze 원본의 **슬롯 누락률**을 매일 계산해 리포트로 남기고, 누락이 있으면 메일로 알리는 Lambda입니다.
spec: [`specs/a-platform/002-missing-rate-report`](../../specs/a-platform/002-missing-rate-report/spec.md)

- **슬롯**: CleanSYS 측정 시각(`mesure_dt`, KST `YYYY-MM-DD HH:MM`)의 30분 단위 값. 하루 48개
- **누락**: 그 슬롯이 정상 원문의 최신 측정 시각으로 한 번도 나타나지 않음 → 영구 손실
- 계산 로직 출처: B(`olchangiagi`)의 `k-tms-bronze` 브랜치 `missing_rate_lambda.py` (커밋 `124f079`)
- 원본 폴더에 확정 표지(`manifest.json`, `_SUCCESS`, spec 007)가 추가돼도 계산 방식은 그대로다(메타·원문 기준). 표지 기준으로 셀지는 아직 정하지 않았다.

## 구성

```
EventBridge Scheduler (매일 09:00, Asia/Seoul)
        │  {}
        ▼
Lambda: tms-missing-rate
        │
        ├──▶ S3 읽기:  tms_cleansys/ingest_date={전날, 당일 UTC}/…   (목록 + 메타 + 원문)
        ├──▶ S3 쓰기:  reports/missing_rate/date=YYYY-MM-DD/report.json
        ├──▶ SNS: tms-collector-alerts ──▶ 이메일   (누락이 있을 때)
        └──▶ CloudWatch Logs: /aws/lambda/tms-missing-rate (보존 14일)

CloudWatch 알람: tms-missing-rate-errors ──▶ SNS ──▶ 이메일   (계산 실패 시)
```

| 항목 | 값 |
|---|---|
| 런타임 | Python 3.13 (표준 라이브러리 + boto3) |
| 핸들러 | `handler.lambda_handler` |
| 메모리 / 제한 시간 | 512MB / 180초 |
| 스케줄 | `cron(0 9 * * ? *)`, `Asia/Seoul` |
| 비동기 재시도 | 0회 |
| 환경 변수 | `BRONZE_BUCKET`, `ALERT_TOPIC_ARN` |
| 인프라 코드 | `infra/stacks/tms-collection` (`module "missing_rate"`), `infra/modules/scheduled-collector` |

## 처리 흐름

1. 대상 날짜를 정합니다. 자동 실행은 어제(KST), 수동 실행은 `from`–`to`.
2. KST 하루는 UTC 이틀에 걸치므로 `ingest_date`가 전날·당일인 폴더를 모두 읽습니다.
3. 폴더마다 상태를 판정합니다: 메타 없음 → `meta_missing`, `inspect.ok`가 아님 → `inspect_fail`, 원문 없음 → `raw_missing`, 그 외 → `ok`(원문의 최신 `mesure_dt`).
4. 기대 슬롯 48개 중 `ok` 폴더의 최신 `mesure_dt`에 없는 것을 누락으로 셉니다.
5. 리포트를 저장합니다(같은 날짜는 덮어씀).
6. 자동 실행이고 누락이 1개 이상이면 SNS로 요약 메일을 보냅니다.

## 알림 두 종류

| 메일 | 언제 | 내용 |
|---|---|---|
| `[TMS] 2026-11-03 슬롯 누락 2개` | 자동 실행에서 누락 발견 | 날짜, 누락 수와 비율, 슬롯 목록, 폴더 상태별 수, 리포트 경로 |
| `ALARM: "tms-missing-rate-errors"` | 계산 자체가 실패 (권한, 시간 초과, 원문 파싱 실패 등) | CloudWatch 알람. 원인은 로그 그룹에서 확인 |

수동 실행(백필)은 누락이 있어도 메일을 보내지 않습니다.

## 권한

| 권한 | 범위 |
|---|---|
| `s3:ListBucket` | 원본 버킷, `s3:prefix` = `tms_cleansys/*` |
| `s3:GetObject` | `tms_cleansys/*` |
| `s3:PutObject` | `reports/missing_rate/*` (원본 경로에는 쓰기 권한 없음) |
| `sns:Publish` | `tms-collector-alerts` |
| 로그 쓰기 | `/aws/lambda/tms-missing-rate` |

API 키(SSM·KMS) 권한은 없습니다.

## 수동 백필

시간 제한 때문에 한 번에 7일 이하로 나눠 호출합니다.

```bash
aws lambda invoke --function-name tms-missing-rate \
  --cli-binary-format raw-in-base64-out \
  --payload '{"from":"2026-11-01","to":"2026-11-03"}' /dev/stdout
```

## 운영 확인

```bash
# 어제 리포트
aws s3 cp s3://smokestack-tms-raw-952900391026/reports/missing_rate/date=$(date -d yesterday +%F)/report.json - | jq '.slots'
```

- 리포트가 없으면 함수가 돌지 않았거나 실패한 것입니다. 로그 그룹 `/aws/lambda/tms-missing-rate`를 확인합니다.
- 누락률 = `slots.missing_count / slots.expected`. 기간 누락률은 날짜별 분자·분모를 각각 더해 계산합니다.

## 알려진 제약

- API 전체 기준입니다. 특정 사업장·배출구만 빠진 경우는 세지 않습니다.
- 누락의 원인(우리 쪽 수집 문제 / API가 그 시각 값을 안 냄)은 구분하지 않습니다.
- 스케줄이 멈춰 이 함수가 아예 안 돌면 알람이 울리지 않습니다(값 없음 = 정상 설정). 그날 리포트가 없는 것으로 알 수 있습니다.
