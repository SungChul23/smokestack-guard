# Contract: 합성 스냅샷 레이아웃

**Spec**: [../spec.md](../spec.md) · 실측 레이아웃은 [001 계약](../../../a-platform/001-tms-collection/contracts/raw-layout.md)을 따른다.

## 경로

```text
tms_synthetic/episode=<에피소드ID>/ingest_date=YYYY-MM-DD/hour=HH/run_ts=YYYYMMDDTHHMMSSZ/
├── snapshot.json.gz       # 원문 (gzip)
├── snapshot.meta.json     # 메타
├── manifest.json          # 확정 표지 (101과 같은 형식)
└── _SUCCESS               # 확정 표지
```

- 실측과 다른 점은 앞의 **`tms_synthetic/`** 와 **`episode=…/`** 두 단계뿐이다. 나머지는 실측과 같다(UTC).
- 쓰기 대상은 `tms_synthetic/` 아래뿐이다. `tms_cleansys/` 아래 경로는 쓰지 않는다.
- 에피소드 ID 예: `S-01-E`, `S-02-E-NOX`, `S-02-E-SOX`, `S-02-E-NOXSOX`.

## 스냅샷 원문

```json
{
  "response": {
    "header": {"resultCode": "0", "resultMsg": "...", "totalCount": 2},
    "body": {
      "items": [
        {"area_nm": "...", "fact_manage_nm": "합성사업장-S01E-01", "stack_code": "SYN-S01E-01",
         "mesure_dt": "2026-11-20 09:00",
         "nox_mesure_value": "62.40", "nox_exhst_perm_stdr_value": "80",
         "sox_mesure_value": null, "sox_exhst_perm_stdr_value": null,
         "...": "tsp, hcl, co, nh3, hf 도 같은 쌍으로 null"}
      ]
    }
  }
}
```

- 항목은 실측과 같은 18필드이며 **그 밖의 필드를 넣지 않는다**.
- 측정값·허용기준은 문자열(측정값 소수 둘째 자리, 허용기준 정수). 상태 문구와 콤마 숫자는 원문 그대로.
- 합성 배출구 코드는 `SYN-` 접두어. 실제 배출구 코드를 쓰지 않는다.
- `totalCount`는 `items` 개수와 같다 (S-07 결함 제외).

## 메타

실측 `snapshot.meta.json`과 같은 키에 더해 생성 정보를 둔다.

| 키 | 값 |
|---|---|
| (실측 키) | `source`(합성 표시), `run_ts`, `saved_at`, `raw_bytes`, `gz_bytes`, `sha256_raw`, `raw_key`, `inspect` |
| `synthetic` | `{"episode_id": ..., "scenario_id": ..., "generator_version": ..., "stats_version": ...}` |

## 정보 파일 (스냅샷 밖, 평가 대조용)

`out/manifest.jsonl`, `out/delivery.jsonl` — 필드는 [data-model.md](../data-model.md). 모델·Silver 입력이 아니다.

## 읽는 쪽 규칙

- Silver가 합성을 읽으려면 읽을 경로 접두어를 지정할 수 있어야 한다(현재 `tms_cleansys/` 고정). 에피소드 단위로도 읽을 수 있어야 한다. 이 변경은 C와 합의한다.
- 합성 결과를 실측과 섞어 학습·성능 비교에 쓰지 않는다.
