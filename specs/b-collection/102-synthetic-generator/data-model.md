# Data Model: K-TMS 합성 데이터 생성기

**Spec**: [spec.md](spec.md) · **Plan**: [plan.md](plan.md)

## 입력

### 참조 통계 `data/ref_stats.csv` (배출구 × 항목 한 줄, 커밋하지 않음)

| 컬럼 | 뜻 |
|---|---|
| `item` | `NOX` / `SOX` |
| `fact_manage_nm`, `stack_code` | 참조 배출구 (둘이 함께 키) |
| `n_valid` | 유효 값 개수 (≥ 200만 사용) |
| `mean`, `std`, `phi` | 기준대비율(%)의 평균, 표준편차, 1단계 자기상관 |
| `p50`, `p99`, `max_pct` | 분위수와 최댓값 |
| `perm_std`, `perm_distinct` | 허용기준 값, 종류 수 (1인 곳만 사용) |
| `items_measured` | `NOX`, `SOX`, `NOX+SOX` |
| `stats_version` | `provisional` / `train-v1` |

### 설정 `config/config.yaml` (값은 임시)

```yaml
run:
  seed: 20261109
  generator_version: gen-v1
  stats_version: provisional
  snapshot_interval_min: 10
  slot_min: 30
  episode_steps: 96
  warmup_steps: 12
  start_kst: "2026-11-20 09:00"
ref_selection:
  min_valid: 200
  normal: {mean: [10, 50], phi: [0.5, 0.95], p99_max: 70}   # S-01 (70% 미만 = 정상 단계)
  trajectory:
    default: {p99_max: 70,  first_value_within_sigma: 2.0}  # S-02, S-04 (첫 값이 정상 단계)
    S-03:    {p99_max: 100, first_value_within_sigma: 2.0}  # 첫 값이 주의·경고 단계(76, 87): 평소 70~90% 수준, 초과는 드문 굴뚝
episodes:                  # 평가·시연용 21개 (변형 × 성분)
  S-01-E: {items: [nox, sox]}
  S-02-E:
    episodes:
      - {suffix: NOX,          items: [nox]}
      - {suffix: SOX,          items: [sox]}
      - {suffix: NOXSOX-NOXUP, items: [nox, sox], rising: [nox]}   # 한 굴뚝·한 행, NOX만 상승
      - {suffix: NOXSOX-SOXUP, items: [nox, sox], rising: [sox]}   # 한 굴뚝·한 행, SOX만 상승
  S-03-E: {variants: [OVER, UNDER], items: [nox, sox]}
  S-04-E: {variants: [EXCEED, SPIKE, PLATEAU], items: [nox, sox]}
  S-05-E: {items: [nox]}
  S-06-E: {items: [nox]}
  S-07-E: {variants: [SAME, CONFLICT], items: [nox]}
  S-08-E: {items: [nox]}
```

상태 단계 기준: 70% 미만 정상, 70~79% 주의, 80~89% 경고, 90~99% 위험, 100% 이상 초과. 라벨(`label-v1`)의 양성 기준 90%는 위험 단계의 시작이다.

### 기대 결과 `expected/S-xx-E.yaml` (생성 전에 작성, 다른 1명이 검수)

| 필드 | 뜻 |
|---|---|
| `scenario_id` | 예 `S-02-E` |
| `items` | 항목 구성 (`NOX`, `SOX`, `NOX+SOX`) |
| `rising` | NOX+SOX 에피소드에서 시나리오 궤적을 따르는 성분. 나머지는 정상 배경 |
| `trajectory_pct` | 고정 궤적(기준대비율 %). 없는 시나리오는 생략. 변형 하나의 궤적은 NOX·SOX가 공유한다 |
| `label_expect` | `label-v1`로 계산한 양성·음성·제외 (궤적 앞 구간 포함, 교차 확인용) |
| `silver_expect` | 현재 구조 기대: 행별 `status`와 `ratio` 범위, 행 수 |
| `later_expect` | 이후 기대: 판정 등급, 사전 경고 기대 (참고용, 자동 대조 대상 아님) |
| `known_mismatch` | 알려진 불일치 (예: 콤마 숫자) 와 사유 |

## 에피소드 계획 (메모리)

| 필드 | 뜻 |
|---|---|
| `episode_id` | `S-01-E-NOX`, `S-02-E-NOXSOX-NOXUP`, `S-03-E-OVER-SOX`처럼 변형·성분 포함 |
| `scenario_id` | 시나리오 (`S-02` 등) |
| `rising` | 오르는 성분(NOX+SOX 에피소드) |
| `stack_codes` | 합성 배출구 코드 `SYN-<에피소드>-<nn>` |
| `ref` | 참조 배출구(`fact_manage_nm`, `stack_code`, 항목) |
| `seed` | 에피소드 seed |
| `start_kst` | 첫 측정 시각 |

## 산출물

### 합성 스냅샷 (경로·모양은 [contracts/synthetic-layout.md](contracts/synthetic-layout.md))

- 항목 `items[]` 한 줄 = 한 배출구의 18필드 (`area_nm`, `fact_manage_nm`, `stack_code`, `mesure_dt`, 항목 7종 × 측정값·허용기준). 실측에 없는 필드를 넣지 않는다.

### 에피소드 정보 `out/manifest.jsonl` (평가 대조용, 모델 입력 아님)

| 필드 | 뜻 |
|---|---|
| `episode_id`, `scenario_id` | 에피소드와 시나리오 |
| `stack_code` ↔ `ref` | 합성 배출구 코드와 참조 배출구 |
| `ref_stats_version`, `generator_version`, `seed` | 재현 정보 |
| `first_mesure_dt`, `last_mesure_dt`, `snapshots` | 범위와 스냅샷 수 |
| `label_counts` | `label-v1` 양성·음성·제외 건수 (평가 대조용, 모델 입력 아님) |
| `defects` | S-06 결함 종류와 위치 |

### 발행 정보 `out/delivery.jsonl`

| 필드 | 뜻 |
|---|---|
| `episode_id`, `run_ts` | 스냅샷과 실행 시각 |
| `stack_code`, `mesure_dt` | 해당 항목 |
| `delay_min` | 측정 시각 대비 늦게 나타난 분 (S-08). 끝내 안 나타나는 값(누락)은 행이 없고 `dropped`로 기록 |
| `duplicate_of` | 같은 값이 이미 나타난 스냅샷 (S-07) |
| `conflict_with` | 같은 측정에 다른 값이 이미 나타난 스냅샷 (S-07 `CONFLICT`) |

## 검증 규칙 (자동 점검)

1. 스냅샷 수·항목 수가 정보 파일과 같다.
2. 구조(`response.header`, `items[]`)와 항목 필드 이름·타입이 실측과 같다 (S-06 제외).
3. 경로가 `tms_synthetic/`이고 배출구 코드가 `SYN-`으로 시작한다.
4. `mesure_dt`가 30분 격자이고, 키 `(배출구, mesure_dt, 항목)`이 유일하다 (S-07·S-08 제외).
5. 값·허용기준이 문자열이고 소수 자릿수가 실측과 같다.
6. 참조가 재지 않는 항목 필드는 빈 값이다.
7. 응답 점검: 결과 코드 `"0"`, 전체 건수 = 항목 수 (S-06 제외).
8. 시나리오별 궤적과 `expected` 대조, `to_silver` 결과 대조.
9. S-01 통계(평균·표준편차 ±10%, φ ±0.1).
