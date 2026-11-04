# Implementation Plan: 대만 CEMS Silver 정제

**Spec**: [spec.md](spec.md) | **Branch**: `10-silver` (이슈 #10) | **Date**: 2026-11-04

## Summary

AQX_P_186 월별 JSONL을 Spark 4.1로 읽어 `silver_cems_30m` → `silver_cems_ml_ready`를 만든다. AQX_P_187은 같은 정제 규칙을 거쳐 검증 전용 `silver_cems_1h_check`로 분리하고, 15분 값 4개 평균과 비교해 `m_time` 구간 의미를 판정한다. 월 단위로 덮어쓰기(멱등) 처리해, 수집이 진행 중인 월부터 차례로 돌릴 수 있게 한다.

## Technical Context

- **언어/런타임**: Python 3.11+, PySpark 4.1 (로컬 우선, 이후 AWS Glue로 이전 가능하게 DataFrame API만 사용)
- **입력**: 월별 JSONL (로컬 `C:\Users\NT551_11TH\AppData\Local\Temp\moenv\YYYY-MM.jsonl`, S3 `s3://smokestack-tms-raw-952900391026/bronze/tw_cems/historical/`). 파일당 2~3GB.
- **출력**: Parquet, `data/silver/<테이블>/month=YYYY-MM/` 파티션 (Git 제외)
- **테스트**: 작은 합성 입력으로 `pytest` 단위 검증 + 월 하나 실데이터 검증(행 수 대조)
- **제약**: Bronze 원본은 읽기 전용. S3 쓰기와 삭제는 하지 않는다.

## Constitution / 팀 규칙 점검

- 원본 보존: Bronze를 수정·삭제하지 않는다. 통과.
- 놓친 데이터 불가: 제외 행도 사유와 함께 보존한다(FR-006). 통과.
- 비밀값: 사용하지 않는다. 통과.
- 외부 패키지: Silver 코드는 수집 Lambda가 아니므로 PySpark·pandas 사용 가능. 통과.
- 브랜치/PR: `10-silver`에서 작업하고 PR로 `main`에 합친다.

## 모듈 구조

```
src/smokestack_guard/silver/cems/
├── schema.py      # 원본 스키마(ImportDate struct 포함), 상수(물질, 허용 코드)
├── clean.py       # 상태코드 판정, 중복·충돌, 제외 사유, 플래그 (FR-001~010)
├── aggregate.py   # 15분 → 30분, ratio_pct, UTC/현지 시각 (FR-003, 005, 008)
├── features.py    # Lag·이동통계·시간 Feature, 라벨 (FR-011~014)
├── check_1h.py    # 187 정제 + 구간 의미 검증 보고서 (FR-015, 016)
├── report.py      # 단계별 행 수·양성 손실 기록 (FR-017)
└── run.py         # 월 단위 CLI: --month YYYY-MM --stage 30m|ml|check
tests/silver/test_cems_*.py
```

기존 `silver/tw_cems.py`(pandas 초안)는 새 모듈이 같은 결과를 내는 것을 확인한 뒤 교체한다.

## 설계 결정

1. **제외 행 보존**: 15분 단위 `cleaned_15m`에 `exclusion_reason`을 붙여 모든 행을 유지하고, 30분 집계에서 `aggregation_status`를 계산한다. 행 수 대조(SC-001)는 이 두 테이블로 한다.
2. **상태코드**: 첫 글자(운전), 둘째 글자(설비), 끝 두 자리(데이터 상태)로 분해. 정책표는 `schema.py` 한 곳에 두고 `quality_policy_version`으로 버전을 기록한다.
3. **시각**: `m_time`을 `Asia/Taipei` 시각으로 해석해 `interval_start_local`·`interval_start_utc`를 둔다. 구간 의미는 US3 결과 전까지 "시작"으로 임시 가정하고 `aggregation_version`에 기록한다. 결과가 "끝"이면 한 칸 이동만 바꾸면 된다.
4. **Feature**: 굴뚝·물질별 윈도우를 시각 기준 `rangeBetween`으로 만들어 결측을 건너뛰지 않는다. 6개 연속 유효 조건은 창 안 유효 건수로 판정한다.
5. **기준 변경**: Feature 창(150분) 안에서 `standard_value`가 달라지면 `feature_valid = false`, 사유 `STD_CHANGED`.
6. **멱등**: 월 파티션 단위로 덮어쓴다. 월 경계 Lag를 위해 `ml` 단계는 앞 달의 마지막 150분을 읽는다.
7. **라벨 경계**: 월 끝 t+60 라벨은 다음 달 데이터가 없으면 NULL로 두고, 다음 달 처리 후 다시 계산한다.

## 단계(구현 순서)

1. 2025-12 한 달로 `clean` + `aggregate` 구현, 행 수 대조 통과 (US1)
2. `check_1h` 구간 의미 검증 → 필요 시 시각 이동 확정 (US3)
3. `features` + 라벨, 누수·라벨 표본 대조 (US2)
4. 24개월 배치 실행과 보고서
5. Glue 이전 검토 (Spark 4.1 지원 여부 확인)

## 위험과 미결

- **Glue의 Spark 4.1 지원**: Glue가 4.1을 지원하지 않으면 로컬·EMR 등 대안을 정해야 한다. 4단계 전에 확인한다.
- **187 원본 위치**: 현재 확인한 187 자료는 일부 로컬 수집분뿐이다. 24개월 187이 S3에 있는지 확인이 필요하다(없으면 US3는 확보분 기간으로 제한).
- **데이터 크기**: 월 2~3GB. 로컬 Spark 메모리 설정과 디스크 여유(출력 포함) 확인이 필요하다.
- **PySpark 설치**: 로컬 `.venv`에 PySpark 4.1과 Java가 있는지 아직 확인하지 않았다.
