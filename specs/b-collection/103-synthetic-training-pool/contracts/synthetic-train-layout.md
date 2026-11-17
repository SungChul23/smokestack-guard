# Contract: 학습용 합성 Bronze 폴더·메시지·manifest

**Spec**: [../spec.md](../spec.md) · **Plan**: [../plan.md](../plan.md) · **구현**: `k_tms_synthetic_train/synth_train/`

학습용 합성 데이터가 실측(`tms_cleansys/`)과 **같은 모양**으로 쌓이도록 정한 약속이다. 합성은 경로(`tms_synthetic_train/`)와 굴뚝 코드(`SYN-T-…`)로만 구분된다. 실측 경로에는 쓰지 않는다.

## 1. Bronze 폴더 구조

```
tms_synthetic_train/
└── ingest_date=YYYY-MM-DD/           # run_ts의 UTC 날짜
    └── hour=HH/                      # run_ts의 UTC 시
        └── run_ts=YYYYMMDDTHHMMSSZ/  # UTC
            ├── snapshot.json.gz      # API 응답 원문(gzip)
            ├── snapshot.meta.json
            ├── manifest.json
            └── _SUCCESS              # 위 데이터 파일을 쓰고 해시를 확인한 뒤에만 생김(빈 파일)
```

- 폴더 하나 = 30분 슬롯 하나의 스냅샷. 하루(KST) 48개.
- `run_ts` = 측정 시각(KST → UTC) + 70분. 지연은 없다(실측의 94.9%가 70분 뒤에 나타나는 것을 따름).
- 평가용(102)은 `tms_synthetic/episode=<id>/…`로 구분한다. 학습용에는 `episode=` 폴더가 없다.
- 저장소: 로컬 폴더 또는 S3 호환 저장소. 쓰기 순서는 항상 **데이터 파일 → 올라간 것을 다시 읽어 `sha256_raw` 확인 → `manifest.json` → `_SUCCESS`**.
- `tms_cleansys/`에는 쓰지 않는다(`writer.check_prefix`가 거부, `tms_synthetic`·`tms_synthetic_train` 두 루트만 허용).

## 2. `snapshot.json.gz` (압축을 풀면)

실측 API 응답과 같은 구조다.

```json
{"response":{"header":{"resultCode":"0","totalCount":<n>,"resultMsg":"NORMAL_CODE"},
             "body":{"items":[ { ...18개 필드... }, ... ]}}}
```

- JSON은 `separators=(",",":")`, `ensure_ascii=false`, UTF-8. gzip은 `mtime=0`이고 헤더의 OS 표지(10번째 바이트)를 `0xff`로 고정한다(Windows·Linux에서 같은 바이트).
- `totalCount` = `items` 개수. 항목은 `stack_code` 순으로 정렬한다.
- 항목(`items[]` 한 줄)은 실측과 같은 **18개 필드**: `area_nm`, `fact_manage_nm`, `stack_code`, `mesure_dt`, 그리고 `nox`·`sox`·`tsp`·`hcl`·`co`·`nh3`·`hf` 각각의 `<name>_mesure_value`, `<name>_exhst_perm_stdr_value`.
- 값은 문자열이다. 측정값은 소수 둘째 자리(`"94.50"`), 허용기준은 필요한 만큼(`"105"`). 합성 굴뚝은 성분 하나(NOX 또는 SOX)만 재고 나머지 필드는 `null`이다.
- `area_nm` = `합성지역`, `fact_manage_nm` = `합성사업장-T-<날짜>-<성분>-<모양>-<번호>`, `stack_code` = `SYN-T-<시작날짜>-<성분>-<모양>-<번호>`(예: `SYN-T-20261116-NOX-SPIKE-001`). 실측 굴뚝 코드와 겹치지 않는다.
- `mesure_dt` = `YYYY-MM-DD HH:MM`(KST, 30분 격자). 한 스냅샷의 모든 항목은 같은 슬롯의 `mesure_dt`를 가진다.
- 값은 **파일에 쓰일 문자열에서 되돌린 비율이 판정에 쓴 곡선 값과 같게** 맞춰져 있다(90% 경계에서 판정이 뒤집히지 않음).

## 3. `snapshot.meta.json`

`source`(`synthetic`), `run_ts`·`requested_at`·`saved_at`(모두 `run_ts`와 같은 UTC 시각), `status_code`(200), `elapsed_ms`(0), `attempts`(1), `raw_bytes`, `gz_bytes`, `sha256_raw`(원문 SHA-256), `raw_key`(`<prefix>/snapshot.json.gz`), `inspect`(`ok`, `result_code`, `total_count`, `item_count`), `synthetic`(`generator_version`, `stats_version`). 모든 시각 필드는 `run_ts`에서 유도하므로 같은 입력은 같은 바이트다.

## 4. `manifest.json` (확정 표지)

`manifest_version`(1), `files`(`snapshot.json.gz`와 `snapshot.meta.json`의 이름·크기·SHA-256), `raw_sha256`, `committed_at`(= `run_ts`). `inspect.ok`가 아니면 만들지 않는다.

## 5. Kafka 메시지

| 항목 | 값 |
|---|---|
| 토픽 | `tms.synthetic.train`, 파티션 1, 보존 기간 제한 없음 |
| 키 | `run_ts` 문자열(`YYYYMMDDTHHMMSSZ`, ASCII 바이트) |
| 값 | 응답 원문 JSON 바이트(`snapshot.json.gz`를 푼 것). 크기 한도 1,000,000바이트 미만 |
| 헤더 `root` | 저장 루트(`tms_synthetic_train`) |
| 헤더 `episode_id` | 학습용은 빈 값(평가용은 에피소드 ID) |
| 헤더 `info` | JSON `{"generator_version": …, "stats_version": …}`(키 순서 보존) |

- 적재 쪽은 메시지에서 `snapshot.make_files`로 파일 4개를 **다시 만든다**. 같은 메시지는 같은 경로·같은 바이트를 만든다(멱등).
- 읽은 위치는 Spark 체크포인트에만 있다(컨슈머 그룹 오프셋을 쓰지 않음).

## 6. `manifest.jsonl` (평가용·선택용 태그, 모델 입력 아님)

`out/manifest/<YYYY-MM-DD>.jsonl`, 하루 파일 하나. **시작 날짜가 그날인 에피소드만** 한 줄씩 적는다(자정을 걸치는 에피소드는 시작한 날에만).

| 필드 | 뜻 |
|---|---|
| `day` | 시작 날짜(KST) |
| `item` | `nox` / `sox` |
| `shape` | `EXCEED` · `PLATEAU` · `OVER` · `SPIKE` · `GRADUAL` · `OTHER` |
| `n` | 같은 (날짜, 성분, 모양) 안의 번호 |
| `stack_code` | 합성 굴뚝 코드 |
| `ref` | 참조 실측 굴뚝(`fact_manage_nm`, `stack_code`) |
| `seed` | 에피소드 seed(재현용) |
| `start_slot` | 시작 슬롯(0~47) |
| `first_mesure_dt`, `last_mesure_dt` | 첫·마지막 측정 시각(KST) |
| `snapshots`, `rows` | 에피소드가 걸친 슬롯 수와 행 수(성분 하나라 같음) |
| `stats_version`, `generator_version` | 재현 정보 |

라벨 건수·합성 음성 수는 `label.py`가 생긴 뒤에 추가한다(후속).

## 7. 실행 상 약속

- 같은 (설정, 날짜)는 어느 환경에서 만들어도 **바이트가 같다**. 날짜를 만드는 순서와도 무관하다.
- 에피소드는 `seed = f(설정 seed, 시작 날짜, 성분, 모양, 번호)`로 통째로 만든다. 자정을 걸치는 에피소드는 다음 날을 만들 때 seed로 다시 만든다(저장된 상태 없음).
- `release`는 어제·오늘·내일 하루치가 없으면 생성하고, `run_ts`가 지금 이전이고 최근 `lookback_min`(기본 180분) 안인 스냅샷만 발행한다(멱등).
