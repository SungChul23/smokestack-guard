# Feature Specification: K-TMS ML-ready에 CO·HCl·TSP 추가

**Feature Branch**: (사람이 이슈에서 만든다)

**Created**: 2026-11-26

**Status**: Implemented (pandas·Spark), 배포·재계산 전

**Input**: 추가 물질 분석(`추가물질_1차분석_2026-11-26`)에서 CO는 학습 후보, HCl·TSP는 양성이 적거나 이력 효과가 불확실해 학습하지 않기로 했다. 학습하지 않더라도 모델 담당과 분석 담당이 같은 규칙(라벨, 이력, 적격)으로 읽을 수 있게 ML-ready에 둔다.

## Requirements

- **FR-001**: `data_source = ktms`(실측 K-TMS)의 ML-ready에 `co`, `hcl`, `tsp` 행을 만든다. 규칙(상태 `ok`, 30분 격자, 라벨, 적격, `partial_history_usable`)은 `nox`·`sox`와 같다.
- **FR-002**: 합성(`ktms_synth`)과 대만(`tw_cems`) 표는 지금처럼 `nox`, `sox`만 만든다.
- **FR-003**: 컬럼·값 계산·`ML_ITEMS`는 바꾸지 않는다. `ml_ready.items_for(data_source)`가 물질 목록을 정한다.
- **FR-004**: pandas와 Spark가 같은 물질을 고른다.

## Out of Scope

- 이 물질들을 학습·채점하는 것. NOx·SOx 모델과 파일은 그대로다.
- `nh3`, `hf`: 넣지 않는다.
- 대만 CO·HCl: 이 spec에서 넣지 않는다.

## 알려진 제약·위험

- **소비하는 쪽이 `item_code`로 거르지 않으면 행이 섞인다.** 모델·평가 코드는 물질을 골라 읽어야 한다. 도은 님께 알려야 한다.
- 행 수·양성 수 통계(`by_item`)에 새 물질이 나타난다.
- 단위(CO·HCl ppm, TSP mg 단위 추정)는 확인하지 못했다. 기준대비율은 단위와 무관하다.
- 다시 계산하기 전 날짜에는 새 물질 행이 없다.
