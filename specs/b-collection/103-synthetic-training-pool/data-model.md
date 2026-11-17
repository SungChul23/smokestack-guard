# Data Model: 학습용 합성 데이터 생성기

**Spec**: [spec.md](spec.md) · **Plan**: [plan.md](plan.md) · **폴더·메시지 계약**: [contracts/synthetic-train-layout.md](contracts/synthetic-train-layout.md)

## 입력

### 참조 통계 `data/ref_stats.csv` (커밋하지 않음)

굴뚝 × 성분 한 줄. 컬럼은 102와 같다: `item`, `fact_manage_nm`, `stack_code`, `n_valid`, `mean`, `std`, `phi`, `p50`, `p99`, `max_pct`, `perm_std`, `perm_distinct`, `items_measured`, `stats_version`. 현재 버전은 **`ref-1030-1110`**(실측 10/30~11/10, 3,131행, 사용 가능 3,062행). 합성 날짜와 통계 기간은 독립이며, 통계를 새로 뽑으면 버전을 올린다.

사용 조건(`stats.usable`): `n_valid ≥ min_valid`(200), `std > 0`, `phi` 있음, `perm_distinct = 1`.

### 설정 `config/daily.yaml`

| 블록 | 필드 | 뜻 |
|---|---|---|
| `run` | `seed`, `generator_version`, `stats_version` | 재현 정보. `seed`는 에피소드 seed의 바탕 |
| `snapshot` | `slot_min`(30), `run_ts_offset_min`(70), `max_message_bytes`(1,000,000) | 슬롯 크기, `run_ts` = 측정 시각 + 오프셋, Kafka 메시지 한도 |
| `release` | `lookback_min`(180) | `release`가 최근 몇 분 안의 스냅샷만 올릴지 |
| `episode` | `warmup_steps`(12), `return_steps`(6), `return_max`(90) | 모양 앞 정상 구간, 뒤 복귀 구간, 복귀 구간 상한(%) |
| `daily_episodes` | `nox`·`sox`별 모양 → 하루 에피소드 수 | 하루 생성량. 아래 표 |
| `ref_selection` | `min_valid`, `groups.low/high`(`p99_max`, `background_max`, `first_value_within_sigma`) | 참조 굴뚝 선택 조건. 모양의 `group`이 어느 조건을 쓸지 정함 |
| `shape_ranges` | 모양별 `group`과 곡선 범위 | 모양 구간을 뽑는 범위(%) |
| `paths` | `stats`, `out` | 입력·출력 위치 |

### 하루 생성량 (시작값, `daily_episodes`)

실측 일평균 양성(NOX 약 403, SOX 약 103)과 1:1을 시작값으로 삼은 **권고값**이다. 값은 설정의 숫자만 바꾸고 코드는 바꾸지 않는다. 선택은 ML 담당자(E) 몫이다.

| 모양 | NOX 에피소드/일 | SOX 에피소드/일 |
|---|---|---|
| OTHER | 125 | 24 |
| SPIKE | 49 | 14 |
| EXCEED | 11 | 7 |
| PLATEAU | 11 | 4 |
| OVER | 11 | 4 |
| GRADUAL | 11 | 4 |
| **합계** | **218** | **57** |

실제 생성 결과(실측 통계, 2026-11-13~16): 하루 에피소드 275개, 행 약 6,000~6,300, 스냅샷 48개.

### 모양 범위 `shape_ranges` (1단계, 제안값)

값은 기준대비율(%)이며 모든 궤적은 `classify_shape`가 의도한 모양으로 판정할 때만 쓰인다(아니면 다시 뽑음).

| 모양 | 그룹 | 범위 |
|---|---|---|
| GRADUAL | low | `ramp_start` 50~69, `ramp_steps` 4~7, `step_rise` 3~9, `entry` 90~99 |
| SPIKE | low | `before` 40~69, `peak` 90~105, `peak_len` 1~2, `after` 40~70 |
| EXCEED | high | `before` 50~89, `peak` 100~130, `exceed_len` 3~6, `after` 60~95 |
| PLATEAU | high | `before` 50~85, `level` 90~99, `hold_len` 4~8, `after` 60~89 |
| OVER | high | `low` 82~89, `high` 90~95, `entries` 3~5 |
| OTHER | high | `before` 70~89, `peak` 90~99, `high_len` 1~3 |

## 모양 판정 (`classify_shape`, label-v1과 같은 90% 기준)

사건 = 90% 이상인 칸을 60분(2칸) 안에서 묶은 것. 우선순위 EXCEED → PLATEAU → OVER → SPIKE → GRADUAL → OTHER.

- EXCEED: 100% 이상 3칸 이상
- PLATEAU: 90% 이상 4칸 이상, 최고 100% 미만, 진입 2회 이하
- OVER: 90% 경계 진입 3회 이상
- SPIKE: 90% 이상 2칸 이하이고 30분 전 70% 미만
- GRADUAL: 직전 4값 엄격 증가, 30분 전 80% 이상, 120분 전 70% 미만
- OTHER: 위에 해당하지 않음

## 에피소드 (메모리, `daily.make_episode`)

| 필드 | 뜻 |
|---|---|
| `day`, `item`, `shape`, `n` | 시작 날짜, 성분, 모양, 번호 |
| `seed` | `f(run.seed, 시작 날짜, 성분, 모양, n)` |
| `start_slot` | 시작 칸(0~47), seed로 정함 |
| `stack_code` | `SYN-T-<날짜>-<성분>-<모양>-<번호>` |
| `ref` | 참조 굴뚝(`fact_manage_nm`, `stack_code`, `mean`, `std`, `phi`, `perm_std`) |
| `curve` | 기준대비율(%) 줄. 파일에 쓰일 문자열 기준으로 맞춘 값 |
| `seg_start`, `seg_end` | 곡선 안의 모양 구간 위치 |

에피소드 길이 = warmup + 모양 구간 + 복귀(약 20~29칸, 하루 48칸 미만). 그래서 하루를 만들 때 **전날 시작분만** 다시 만들면 자정을 걸친 부분이 채워진다.

## 점검 규칙 (`validate`)

1. 폴더 경로가 `tms_synthetic_train/ingest_date=/hour=/run_ts=` 형식이고 날짜·시가 `run_ts`와 같다
2. 파일 4개가 모두 있고(`_SUCCESS` 포함) 해시가 meta·manifest와 같다
3. 응답 코드 `"0"`, `totalCount` = 항목 수
4. 항목이 실측과 같은 18개 필드, 값 형식(소수 둘째 자리, 허용기준 숫자 문자열), 30분 격자
5. 합성 굴뚝 코드 형식(`SYN-T-…`)이고 실측 굴뚝 코드와 겹치지 않음(`real_codes`로 전달)
6. 하루마다 슬롯 48개, 항목의 `mesure_dt`가 슬롯과 같음
7. (굴뚝, 측정 시각) 중복 없음
8. manifest 에피소드마다 측정 시각이 끊김 없이 이어지고(자정 걸침 포함), 곡선을 `classify_shape`로 판정한 모양이 manifest와 같음(데이터 끝을 넘는 에피소드는 건너뜀)
