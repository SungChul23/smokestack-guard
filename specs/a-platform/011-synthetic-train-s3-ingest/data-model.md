# Data Model: 학습용 합성 K-TMS 데이터 AWS Bronze 적재

## 1. S3 경로 (원본 버킷 `smokestack-tms-raw-952900391026`)

```
tms_synthetic_train/
├── ingest_date=YYYY-MM-DD/hour=HH/run_ts=YYYYMMDDTHHMMSSZ/   # B 계약 §1 그대로 (UTC)
│   ├── snapshot.json.gz
│   ├── snapshot.meta.json
│   ├── manifest.json
│   └── _SUCCESS
├── _manifest/YYYY-MM-DD.jsonl       # 에피소드 태그, 시작 날짜(KST)별 (B 계약 §6)
└── _ref_stats/<stats_version>.csv   # 참조 통계 (사람이 올림, 덮어쓰지 않음)
```

- `run_ts` = 측정 시각(KST) + 70분 → UTC. 하루(KST) 48폴더, 매시 :10·:40.
- `_`로 시작하는 폴더는 테이블이 아니다(`AGENTS.md`).

## 2. Lambda 입력

| `mode` | 필드 | 누가 | 동작 |
|---|---|---|---|
| `regular`(기본) | `scheduled_time`(ISO, 없으면 현재 시각) | 정기 스케줄 | `run_ts ∈ (T−180분, T]`이고 `_SUCCESS` 없는 슬롯을 씀 |
| `backfill` | `from`, `to`(KST 날짜, 31일 이내) | 사람 | 각 날짜 48슬롯 중 `run_ts ≤ 지금`이고 `_SUCCESS` 없는 것 |
| `check` | `day`(기본 어제 KST) | 점검 스케줄 | 48슬롯 `_SUCCESS` 확인, 모자라면 SNS |
| (재처리) | DLQ 메시지 본문 또는 그 안의 `requestPayload` | 사람 | 원래 입력으로 다시 실행 |

## 3. Lambda 출력 (로그에도 한 줄 JSON)

| 필드 | 설명 |
|---|---|
| `mode` | 실행 모드 |
| `window` | `[시작, 끝]`(regular) 또는 날짜 범위 |
| `written` | 이번에 쓴 `run_ts` 목록 |
| `skipped` | `_SUCCESS`가 있어 건너뛴 수 |
| `manifest_written` | 이번에 쓴 `_manifest` 날짜 |
| `missing` | (check) 빈 슬롯 `run_ts` 목록 |
| `generator_version`, `stats_version` | 사용한 버전 |

오류는 예외로 끝나고 재시도·DLQ로 간다. 로그에는 경로·건수·버전만 남기고 값은 남기지 않는다.

## 4. DLQ 메시지

| 출처 | 본문 |
|---|---|
| Scheduler DLQ | 원래 입력 JSON(`{"mode":"regular","scheduled_time":…}`) + 오류 속성 |
| Lambda 실패 목적지 | `{"requestContext":{…,"condition":"RetriesExhausted"},"requestPayload":{원래 입력},"responsePayload":{"errorMessage":…}}` |

## 5. 버전 기록표 (quickstart §8에 유지)

| 적용 시작(KST 날짜) | generator_version | stats_version | 바꾼 내용 | 기록자 |
|---|---|---|---|---|
| 2026-10-30 | gen-train-v1 | ref-1030-1110 | 최초 | A |
