# 계약: 호출 입력

함수 `tms-missing-rate`가 받는 이벤트.

## 자동 실행 (Scheduler)

```json
{}
```

- 대상: 실행 시점 기준 어제(KST) 하루
- 누락이 있으면 알림을 보낸다

## 수동 실행 (백필)

```json
{ "from": "2026-11-01", "to": "2026-11-03" }
```

| 필드 | 필수 | 설명 |
|---|---|---|
| `from` | ✅ | 시작 KST 날짜 (`YYYY-MM-DD`) |
| `to` | | 종료 KST 날짜(포함). 없으면 `from` 하루 |

- 날짜마다 리포트를 저장(덮어쓰기)하고, **알림은 보내지 않는다.**
- 시간 제한(180초) 때문에 한 번에 7일 이하로 나눈다.
- `from` > `to`이면 아무 날짜도 계산하지 않는다.

```bash
aws lambda invoke --function-name tms-missing-rate \
  --cli-binary-format raw-in-base64-out \
  --payload '{"from":"2026-11-01","to":"2026-11-03"}' /dev/stdout
```
