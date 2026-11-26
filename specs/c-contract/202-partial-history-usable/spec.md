# Feature Specification: 부분 이력 사용 가능 열

**Feature Branch**: `49-partial-history-usable-column` (이슈 #49)

**Created**: 2026-11-26

**Status**: Implemented (pandas·Spark), 배포·재계산 전

**Input**: ML-ready에서 직전 3시간 중 일부가 비어 학습에서 빠지는 행 가운데, 라벨과 직전 30분 값이 있는 행을 모델 쪽이 골라 쓸 수 있게 열로 표시한다.

## 배경

- `classification_eligible`은 직전 3시간 6슬롯이 모두 있어야 참이다. 슬롯이 빠진 행은 피처가 NaN이라 학습·채점에서 빠진다.
- 11/11~24 K-TMS 재검증(`부분이력_재검증_누적`)에서 직전 3시간이 빈 행의 양성 비율이 높았다. SOx는 같은 방향이고 양성이 적어 누적 중이다. NOx는 재현됐지만 NOx 학습에는 쓰지 않기로 했다.
- 이 행들은 표에 이미 있고 빈 칸이 NaN일 뿐이다. 새로 계산할 값은 없고 어떤 행이 쓸 만한지 표시만 필요하다.

## Requirements

- **FR-001**: `ml_ready.COLUMNS` 맨 끝(37번째)에 `partial_history_usable`(boolean)을 추가한다. 기존 36개 열의 값과 순서는 바꾸지 않는다.
- **FR-002**: 값은 `~feature_valid & label_entry_60m 있음 & ratio_lag_30m 있음 & 기준값 변경 없음`이다.
- **FR-003**: `classification_eligible`과 동시에 참이 될 수 없다. 빈 칸은 NaN으로 두고 보간·0 채움을 하지 않는다.
- **FR-004**: pandas(`ml_ready.py`)와 Spark(`ml_ready_spark.py`)가 같은 값을 낸다.
- **FR-005**: 계약 검사가 FR-002·FR-003을 위반한 행을 잡는다.
- **FR-006**: 기존 Iceberg 표는 잡이 `ADD COLUMNS`로 열을 추가한다. 추가 전 행은 null이다.
- **사용 규칙**: **SOx 학습·채점에만 쓴다.** NOx 학습에는 쓰지 않고 `classification_eligible`만 쓴다(모델 담당과 정함). 열은 모든 물질에 계산하지만 사용은 물질별로 다르다.

## Out of Scope

- 추가 물질(CO·HCl·TSP): ML-ready 항목에 넣지 않는다(`ML_ITEMS` 유지). 분석은 Silver에서 직접 읽어 한다.
- 부분 이력 행으로 학습한 모델의 성능 판단: 모델 담당 몫이다.

## 알려진 제약

- 추가 전 행은 null이라 재계산(`rerun`) 전에는 과거 구간에서 쓸 수 없다.
- SOx 근거는 양성 수가 적어(11/24까지 87건) 방향만 확인한 상태다.
