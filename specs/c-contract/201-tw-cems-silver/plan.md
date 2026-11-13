# Implementation Plan: 대만 CEMS Silver 정제

**Spec**: [spec.md](spec.md) | **Branch**: `10-silver-ktms-contract` (이슈 #10), `14-silver-tw-cems-spark` (이슈 #14) | **Date**: 2026-11-04 | **Updated**: 2026-11-06

## Summary

AQX_P_186 월별 JSONL의 모든 항목·상태코드를 30분 슬롯으로 변환해 `tw_cems`(Silver)를 만들고, 그중 모델 대상(`ok`, `nox`/`sox`, `ppm`)으로 `tw_cems_ml_ready`를 만든다. Silver는 쓸 수 없는 구간의 값도 `status`와 함께 보존하므로, 학습 허용 범위를 넓혀도 Silver를 다시 만들 필요가 없다. 의미 기준선은 pandas 구현이고, 같은 규칙의 Spark 구현을 AWS Glue에서 월 단위로 실행한다. 1시간 자료(AQX_P_187)는 `m_time` 의미 검증에만 쓰고 저장하지 않는다.

## Technical Context

- **언어/런타임**: Python 3.11+. pandas 구현(기준선), PySpark 3.5 구현. **Spark 3.5 기준** — Glue 5.0(3.5.4)·5.1(3.5.6)이 지원하는 최신 계열이며 Glue에는 Spark 4.x가 없다. 코드는 Spark 3.3 이상 API만 쓴다.
- **입력**: 월별 JSON Lines. S3 `s3://smokestack-tms-raw-952900391026/bronze/tw_cems/historical/YYYY-MM.jsonl` (월 2~3GB). 읽기 전용.
- **출력**: Parquet. 로컬은 `data/silver/<테이블>/part.parquet`(Git 제외), Glue는 `year=YYYY/month=MM` 파티션. S3 출력 위치는 미정(A와 확정).
- **테스트**: 합성 입력 단위 테스트(pandas 19개 + Spark 패리티 1개), 실데이터 샘플 패리티(`scripts/validate_spark_parity.py`). Spark 테스트는 Docker(Linux, Java 17)에서 실행하고 PySpark가 없는 환경에서는 건너뛴다.
- **외부 패키지와 이유**: pandas·numpy(Silver 변환), pyarrow(Parquet), pyspark(Glue 실행). Silver는 수집 Lambda가 아니므로 허용된다. Glue 이미지에 pandas가 없으면 `--additional-python-modules`로 추가한다.
- **제약**: Bronze는 읽기 전용이며 S3 원본을 삭제·덮어쓰지 않는다.

## Constitution / 팀 규칙 점검

| 원칙 | 점검 |
| --- | --- |
| I 수집 연속성 | 수집 스케줄·원본을 건드리지 않는다. Bronze 읽기 전용. 통과 |
| II 비밀값 비공개 | 비밀값을 쓰지 않는다. 통과 |
| III 코드로 만들고 적용은 사람이 | Glue 작업·IAM·S3 출력은 **Terraform으로 A가 만든다**(이 plan 범위 밖). AI는 `apply`하지 않는다. 아래 권한 목록 참고 |
| IV 데이터 계약 우선 | Silver 계약(K-TMS 계약 9개 + 대만 전용 4개)과 ML-ready 36개 컬럼(35개 + `data_source`)을 spec의 Key Entities에 정의했다. 계약 변경이라 **C(본인) 리뷰와 영향받는 E에게 PR로 알림**이 필요하다 |
| V 같은 조건의 정직한 비교 | 해당 없음(모델 비교는 E의 spec) |
| VI 설명 가능한 결과 | `status`와 원본 `code2`로 어떤 슬롯이 왜 쓰이지 않는지 추적할 수 있다. 통과 |

**Glue에 필요한 최소 권한(안)**: `bronze/tw_cems/historical/*` 읽기(`s3:GetObject`, `s3:ListBucket`), `silver/tw_cems/*` 쓰기(`s3:PutObject`, `s3:DeleteObject`는 파티션 덮어쓰기에 필요), CloudWatch Logs. Bronze 접두사에는 쓰기·삭제를 주지 않는다.

**비용 영향**: Glue 작업은 월 1회 이하 실행한다. 월 2~3GB 입력의 실행 시간·DPU는 아직 측정하지 않았다(tasks T031). 측정 후 A에게 알린다.

## 구조

```
src/smokestack_guard/silver/
├── tw_cems.py          # Silver (pandas, 의미 기준선): prep → to_silver → build
├── tw_cems_spark.py    # Silver (Spark): tw_cems.py의 상수를 가져와 같은 규칙을 DataFrame API로
└── ml_ready.py         # ML-ready (pandas): Feature·정답·학습 가능 플래그
scripts/
├── glue_tw_cems_silver.py     # Glue 작업 진입점
└── validate_spark_parity.py   # 같은 원본으로 pandas·Spark 결과 비교
tests/
├── test_silver.py             # pandas Silver·ML-ready 단위 테스트
└── test_silver_spark.py       # Spark 패리티 (PySpark 없으면 건너뜀)
spark_migration_checklist.md   # Docker(Spark 3.5) 검증 방법과 Glue 실행 정보
```

처음 설계했던 6개 모듈(`schema`, `clean`, `aggregate`, `features`, `check_1h`, `report`, `run`)은 만들지 않았다. 변환이 단일 함수로 충분했고, 15분 단위 `cleaned_15m` 테이블과 원본 행별 `exclusion_reason`은 슬롯 단위 `status`로 대체했다(spec FR-006).

## 설계 결정

1. **모든 항목·코드를 변환하고 선택은 ML-ready에서**: 허용 코드·항목을 바꿔도 Silver 재실행이 필요 없다. 대가로 Silver 행이 약 3배(36개월 8,038만 행)로 늘었다.
2. **`status` 5종**: `ok`, `not_monitored`, `other_code`, `partial`, `invalid`. 값이 있으면 코드와 상관없이 보존하고 학습 사용 여부만 `status`로 구분한다.
3. **시각**: `m_time`은 대만 시각이고 구간 **시작**이다(1시간 자료와 대조해 확인). `ts_local`은 대만 시각, `ts_kst`는 +1시간. 시각 파싱은 `ISO8601`로 `T`/공백, 초 유무를 모두 처리한다.
4. **단위 보존**: 항목마다 단위가 달라 `unit`을 컬럼으로 두고 환산하지 않는다. 같은 항목이라도 단위가 다르면 별도 행이다.
5. **Feature**: 굴뚝·물질별로 30분 격자에 놓고 시간 기준으로 계산해 빈 구간을 건너뛰지 않는다. 6개 연속 유효 조건은 `feature_valid`다.
6. **멱등**: pandas는 같은 입력에 같은 결과를 낸다. Spark는 동적 파티션 덮어쓰기로 같은 달을 다시 쓰면 그 달 파티션만 교체한다(로컬 확인). ML-ready는 월 경계 Lag를 위해 **월을 합친 뒤** 계산한다.
7. **두 구현의 일치**: 상수·항목 매핑·허용 코드·컬럼 목록을 `tw_cems.py`에서 가져와 `tw_cems_spark.py`가 쓴다. 규칙이 한쪽만 바뀌지 않도록 패리티 테스트를 둔다.

## 단계(구현 순서)와 상태

1. Silver 변환(pandas), 단위 테스트 — **완료**
2. ML-ready, 라벨·누수 단위 테스트 — **완료**
3. `m_time` 의미 검증(US3) — **완료**: 시작 해석 100% 일치
4. 36개월 전체 실행 — **완료**(2026-11-10, 재수집 원본 `bronze2/tw_cems/` 기준): 원본 1억 5,973만 행 → Silver 8,038만 행 → ML-ready 1,844만 행(학습 가능 1,416만 행, 양성 181,231행)
5. Spark 이식과 패리티 검증 — **완료**(Docker, 샘플 3개 달 모든 컬럼 일치)
6. Glue 실행과 월 전체 비교 — **남음** (출력 위치·권한, 비용 측정)
7. 월별 단계별 행 수·양성 수 기록, 표본 검증(SC-003, 004, 006) — **남음**
8. ML-ready Spark 이식 — **PR #37 머지**(성철 님): Glue 실행과 pandas 35컬럼 비교 일치. 학습용은 `tms_silver2.tw_cems_ml_ready`

## 위험과 미결

- **Glue 실행 미검증**: 로컬 Docker(Spark 3.5.4)에서만 확인했다. Glue 이미지의 pandas 유무, S3 권한, 실행 시간은 실행해 봐야 안다.
- **S3 출력 위치·권한**: `silver/` 접두사가 아직 없다. A와 확정한다.
- **원본 공백**: 2023-11은 11-27 16:30에서 끊기고 2023-12는 첫 6시간 반이 없다. 필요하면 재다운로드한다.
- **Open Questions**(spec 참고): 기준 변경 처리, 음수·극단값, `NB`/`AA` 학습 포함, 산소 보정.
- **Spark 4.x**: Glue가 지원하지 않아 쓰지 않는다. 다른 실행 환경(EMR 등)을 쓸 때만 검토하며, ANSI 모드 때문에 `cast` 변환을 `try_cast`로 바꿔야 할 가능성이 크다.

## Complexity Tracking

위반 없음.
