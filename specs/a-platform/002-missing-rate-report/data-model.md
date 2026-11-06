# Data Model: Bronze 슬롯 누락률 일일 리포트

## 입력: 원본 (001 계약)

[001 contracts/raw-layout.md](../001-tms-collection/contracts/raw-layout.md)를 그대로 따른다. 이 기능이 읽는 것은 다음 두 가지다.
- `tms_cleansys/ingest_date={D-1, D}/…/run_ts=…/snapshot.meta.json`의 `inspect.ok`
- 같은 폴더 `snapshot.json.gz`의 `response.body.items[].mesure_dt`

## 슬롯

| 속성 | 값 |
|---|---|
| 형식 | `YYYY-MM-DD HH:MM` (KST, `mesure_dt`와 동일) |
| 하루 기대 수 | 48 (`00:00`, `00:30`, …, `23:30`) |
| 수집됨 | 대상 날짜 계산에 읽은 폴더 중 `status = ok`인 폴더의 최신 `mesure_dt` 집합에 포함 |

## 회차 폴더 요약 (계산 중간값, 저장하지 않음)

| 필드 | 설명 |
|---|---|
| `run` | 폴더 경로 (`…/run_ts=YYYYMMDDTHHMMSSZ`) |
| `status` | 아래 판정 순서의 첫 결과 |
| `latest` | `status = ok`일 때 원문 항목들의 최대 `mesure_dt`, 그 외 `null` |

판정 순서:
```text
메타 없음                  → meta_missing
메타.inspect.ok != true    → inspect_fail
원문 없음                  → raw_missing
그 외                      → ok (latest 계산)
```

## 일일 리포트

위치: `reports/missing_rate/date=YYYY-MM-DD/report.json` (날짜 = 대상 KST 날짜). 스키마: [contracts/report.schema.json](contracts/report.schema.json)

| 필드 | 설명 |
|---|---|
| `target_date_kst` | 대상 날짜 |
| `generated_at` | 생성 시각 (UTC) |
| `folders_in_day` | 대상 KST 하루 안에 `run_ts`가 있는 폴더 수 |
| `slots.expected` | 48 |
| `slots.missing_count` | 누락 슬롯 수 |
| `slots.missing` | 누락 슬롯 목록 |
| `inspect_fail`, `meta_missing`, `raw_missing` | 대상 하루 폴더 중 상태별 수 |

- 누락률 = `slots.missing_count / slots.expected`. 리포트에는 저장하지 않고 읽는 쪽이 계산한다(기간 합산 시 분모·분자를 따로 더해야 하므로).
- 같은 날짜를 다시 계산하면 덮어쓴다. 버킷 버전 관리로 이전 결과도 남는다.

## 실행 결과 (함수 반환값·로그)

날짜마다 `{date, report_key, missing_slots, inspect_fail}`. 자동 실행이면 `alerted: true/false`를 덧붙인다.

## 상태 전이 (자동 실행 1회)

```text
시작 → 어제(KST) 계산 → 리포트 저장
   ├─ 누락 0  → 종료 (알림 없음)
   ├─ 누락 ≥1 → SNS 발행 → 종료
   └─ 예외(권한, 시간 초과, 원문 파싱 실패, 발행 실패) → Errors +1 → 일일 알람 (재시도 없음)
```
