# 계약: 원본(Bronze) 저장 구조

**제공**: 001 수집 Lambda (A) · **소비**: Silver 정제(C), 002 누락률 리포트(A), 분석(D, E)

변경하려면 C의 리뷰와 소비자 공지가 필요하다(원칙 IV).

## 버킷

`smokestack-tms-raw-952900391026` (`ap-northeast-2`)

## 경로

```text
tms_cleansys/
├── ingest_date=YYYY-MM-DD/          # run_ts의 UTC 날짜
│   └── hour=HH/                     # run_ts의 UTC 시 (00–23)
│       └── run_ts=YYYYMMDDTHHMMSSZ/ # 10분 단위, 초는 항상 00
│           ├── snapshot.json.gz     # API 응답 원문 gzip
│           └── snapshot.meta.json   # 메타 (snapshot-meta.schema.json)
└── _state/
    └── latest.json                  # 상태 (state.schema.json)
```

## 보장

1. `run_ts` 폴더는 **응답이 바뀐 회차에만** 생긴다. 폴더가 없는 회차는 "실행 안 됨"이 아니라 "직전과 같음"일 수 있다. 실행 여부는 `_state/latest.json`의 `last_checked_at` 또는 CloudWatch 지표로 판단한다.
2. 원문은 API 바이트 그대로다. 변환·필터·정렬하지 않는다.
3. 원문과 메타는 같은 폴더에 함께 있다. 원문이 먼저 저장되므로, 저장 도중 실패하면 원문만 있고 메타가 없는 폴더가 생길 수 있다.
4. `inspect.ok = false`인 폴더도 지우지 않는다. 소비자는 메타의 `inspect.ok`를 보고 걸러야 한다.
5. 객체는 삭제하지 않고 수명 주기 만료도 없다. 같은 키에 다시 쓰면 이전 버전이 남는다.
6. `ingest_date`, `hour`는 UTC다. 한국 날짜 하루를 읽으려면 UTC 이틀치(전날, 당일)를 읽어야 한다.

## 소비자를 위한 메모

- Hive 스타일 파티션(`key=value`)이라 Glue/Athena/Spark에서 파티션으로 인식된다.
- `_state/`는 파티션이 아니다. 크롤러·테이블 위치에서 제외한다.
- 같은 측정 시각(`mesure_dt`)의 값이 여러 스냅샷에 반복될 수 있다(정정·순서 변경). 중복 제거 기준은 Silver 계약에서 정한다.
