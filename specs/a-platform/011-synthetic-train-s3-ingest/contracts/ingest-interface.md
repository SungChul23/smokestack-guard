# Contract: 합성 적재 Lambda 입출력과 운영 명령

Lambda 이름: `tms-synthetic-train` (ap-northeast-2). Bronze 폴더·파일 형식은 [B 계약](../../../b-collection/103-synthetic-training-pool/contracts/synthetic-train-layout.md) §1~§4를 그대로 따른다.

## 1. 입력

```json
{"mode": "regular", "scheduled_time": "2026-11-17T10:10:00+09:00"}
{"mode": "backfill", "from": "2026-10-30", "to": "2026-11-16"}
{"mode": "check", "day": "2026-11-16"}
```

- 정기 스케줄은 `scheduled_time`에 `<aws.scheduler.scheduled-time>`을 넣는다(UTC ISO).
- 알 수 없는 `mode`, 31일 초과 백필, 날짜 형식 오류는 쓰기 전에 실패한다.

## 2. 수동 실행

```bash
# 슬롯 하나 시험 / 지금 기준 정기 실행
aws lambda invoke --region ap-northeast-2 --function-name tms-synthetic-train \
  --cli-binary-format raw-in-base64-out --payload '{"mode":"regular"}' /dev/stdout

# 백필 (31일 이내, 오래 걸리면 범위를 나눔)
aws lambda invoke --region ap-northeast-2 --function-name tms-synthetic-train \
  --cli-binary-format raw-in-base64-out --cli-read-timeout 900 \
  --payload '{"mode":"backfill","from":"2026-10-30","to":"2026-11-16"}' /dev/stdout

# 점검
aws lambda invoke --region ap-northeast-2 --function-name tms-synthetic-train \
  --cli-binary-format raw-in-base64-out --payload '{"mode":"check","day":"2026-11-16"}' /dev/stdout
```

## 3. 재처리 (DLQ)

```bash
URL=$(aws sqs get-queue-url --region ap-northeast-2 --queue-name tms-synthetic-train-dlq --query QueueUrl --output text)
aws sqs receive-message --region ap-northeast-2 --queue-url "$URL" --max-number-of-messages 10 \
  --query 'Messages[].[ReceiptHandle,Body]' --output text
```

- 본문에 `requestPayload`가 있으면 그 값을, 없으면 본문 전체를 `--payload`로 넘겨 다시 실행한다.
- 성공하면 `delete-message`로 지운다. 이미 채워진 슬롯은 건너뛰므로 두 번 실행해도 결과가 같다.
- 이틀 넘게 지난 슬롯을 채웠다면 그 날짜로 합성 매일 갱신을 다시 실행한다(US4 이후).

## 4. 알림

| 경우 | 제목 (ASCII) | 본문 |
|---|---|---|
| DLQ에 메시지 | CloudWatch 알람 `tms-synthetic-train-dlq-not-empty` | 알람 기본 문안 + 재처리 안내는 이 문서 §3 |
| 점검: 빈 슬롯 | `[tms] synthetic train missing slots - <day> (<n>/48)` | 날짜, 빈 슬롯 `run_ts` 목록(최대 48), 재실행 명령(`backfill` 그 날짜), 이 문서 경로 |

## 5. 출력

data-model §3.
