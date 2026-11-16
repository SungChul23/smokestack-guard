---
description: "103 K-TMS 학습용 합성 데이터 풀 (생성 + Kafka → Spark → Bronze 적재) 작업 목록"
---

# Tasks: K-TMS 학습용 합성 데이터 풀 (생성 + Kafka → Spark → Bronze 적재)

**Input**: `specs/b-collection/103-synthetic-training-pool/` (spec.md, plan.md)

**Tests**: `pytest`를 쓴다(plan). 각 단계의 구현 작업 앞에 그 단계의 테스트를 먼저 쓰고, 실패(빨간불)를 확인한 뒤 구현한다. Kafka·Spark 종단 검증은 Docker가 필요한 통합 검증으로 분리한다.

**Organization**: 사용자 스토리별 단계. 풀을 **파일 모드로 만드는 데까지(Phase 1~6)**가 MVP이고, Kafka → Spark → Bronze 적재(Phase 7)는 102의 평가용 16개 에피소드로 먼저 검증할 수 있어 **Phase 2~6과 병렬로** 진행할 수 있다.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: 다른 파일이고 선행 작업이 없어 병렬 가능
- **[Story]**: US1(모양별 풀 선택), US2(일별 1:1 · 하한 우선 배분), US3(Kafka → Spark → Bronze 적재), US4(점검), US5(곡선 단계화)
- 🧑 표시는 **사람이 하는 작업**(Athena·Docker 실행, 다른 담당 합의, 검수, push). 에이전트는 실행하지 않는다.

## 경로

- 코드: `k_tms_synthetic/synth/`, `k_tms_synthetic/ingest/`, `k_tms_synthetic/kafka/`
- 테스트: `k_tms_synthetic/tests/`, 통합 검증: `k_tms_synthetic/tests/integration/`
- 설정: `k_tms_synthetic/config/pool.yaml`
- 입력(커밋 안 함): `k_tms_synthetic/data/ref_stats.csv`, `daily_targets.csv`, `shape_events.csv`
- 출력(커밋 안 함): `k_tms_synthetic/out/`

---

## Phase 1: Setup · 선행 확인 (plan 단계 0)

**Purpose**: plan의 가정을 확인하고 입력을 준비한다. 가정이 틀리면 plan을 먼저 고친다.

- [ ] T001 🧑 Athena에서 `n_snap` 분포 쿼리를 실행해 **같은 (굴뚝, 측정 시각)이 한 번만 나타나는지** 확인한다. 결과로 plan D1(슬롯마다 스냅샷 1개)을 확정한다. 다르면 plan을 수정한다.
- [ ] T002 🧑 실측 `run_ts`와 `mesure_dt`의 차이(수집 시각이 측정 시각보다 얼마나 늦는지)를 쿼리로 확인해 합성 `run_ts` 규칙(plan 미결 항목)을 정한다.
- [ ] T003 🧑 재료 구간(2026-10-30 ~ 11-10)으로 참조 통계를 다시 뽑아 `data/ref_stats.csv`에 둔다. `stats_version`은 구간이 드러나는 이름(예: `ref-1030-1110`)으로 한다.
- [ ] T004 🧑 재료 구간의 **일별 × 성분 실측 양성 수**를 뽑아 `data/daily_targets.csv`(`day, item, pos`)로 둔다. (일별 양성 쿼리 결과를 재사용한다.)
- [ ] T005 🧑 재료 구간의 **성분 × 모양별 직전 단서 사건 수**를 뽑아 `data/shape_events.csv`(`item, shape, events, events_with_lead`)로 둔다. (모양 분류 쿼리를 재료 구간으로 다시 실행한다.)
- [ ] T006 `synth.snapshot.make_files`가 **같은 입력으로 두 번 호출하면 바이트가 같은지**, meta의 시각 필드가 `run_ts`에서 결정적으로 유도되는지 확인하는 테스트를 `tests/test_snapshot.py`에 추가한다. 실패하면 `make_files`를 고친다(plan D10).
- [ ] T007 [P] `config/pool.yaml` 초안을 plan 스키마로 만든다: `period`(재료 구간), `base_ratio`, `allocation`, `min_events`, `per_shape_cap`, `max_synthetic_share`, `episode`(warmup, 복귀 길이), `shape_ranges`, `seed`, 경로.
- [x] T008 🧑 GitHub 이슈(#50)를 만들고 "Create a branch"로 브랜치를 만든다(바탕은 `29-k-tms-synthetic`). 이 spec 폴더(103)를 그 브랜치로 옮긴다. `.github/CODEOWNERS`에 `/k_tms_synthetic/`이 있는지 확인한다.

**Checkpoint**: 입력 3개와 설정이 있고, plan의 가정(스냅샷 구조, `run_ts` 규칙, `make_files` 결정성)이 확인됐다.

---

## Phase 2: Foundational — 라벨과 모양 판정 (모든 스토리의 전제)

**Purpose**: 풀 계획·생성·점검이 모두 쓰는 두 함수를 먼저 만든다.

### 테스트 먼저

- [ ] T009 [P] `tests/test_label.py`: 102의 평가용 16개 에피소드를 생성해 `compare.read_ratios`로 읽고, `label.count_labels`의 양성·음성·제외가 `expected/*.yaml`의 `label_expect`와 모두 일치하는지 확인한다. 현재 90% 이상, 미래 값 없음, 마지막 2행 제외 경계 케이스를 별도로 테스트한다. (102의 T055~T058을 이 작업이 대신한다.)
- [ ] T010 [P] `tests/test_classify_shape.py`: 102의 고정 궤적 6개가 기대 모양으로 판정되는지 확인한다 — `[56,58,113,109,104,71,60]`→EXCEED, `[59,61,92,95,93,96,94,70,62]`→PLATEAU, `[87,91,88,92,89,91]`→OVER, `[59,61,94,63,60]`→SPIKE, `[62,69,76,82,87,92]`→GRADUAL, 해당 없음→OTHER. 판정 우선순위(EXCEED가 OVER보다 먼저)와 GRADUAL의 "직전 4값 모두 유효" 조건도 테스트한다.

### 구현

- [ ] T011 `synth/label.py`: `label-v1` 규칙(현재 90% 미만, t+30 또는 t+60이 90% 이상이면 양성, 둘 다 유효하고 90% 미만이면 음성, 현재 90% 이상이거나 미래 값이 없으면 제외, 에피소드 마지막 2행 제외, 반올림 없음)으로 건수를 센다. T009가 통과해야 한다.
- [ ] T012 `synth/shapes.py`에 `classify_shape`를 구현한다(사건 = 90% 이상 행을 60분 재진입으로 묶음, EXCEED → PLATEAU → OVER → SPIKE → GRADUAL → OTHER 순서). T010이 통과해야 한다.

**Checkpoint**: 102의 16개 에피소드로 라벨 건수가 expected와 일치하고, 고정 궤적이 올바른 모양으로 판정된다.

---

## Phase 3: User Story 2 — 일별 1:1 총량과 하한 우선 배분 (P1) 🎯 MVP

**Goal**: 데이터를 만들기 전에 **계획 단계에서** 일별 합성량과 (성분 × 모양)별 배정을 검증한다.

**Independent Test**: `data/daily_targets.csv`와 `data/shape_events.csv`만으로 풀을 계획하고 요약 표를 확인한다(데이터 생성 없음).

### 테스트 먼저

- [ ] T013 [P] [US2] `tests/test_pool.py::test_daily_budget`: 일별 합성 양성 수의 합이 `그날 실측 양성 × base_ratio`와 같다(성분별).
- [ ] T014 [P] [US2] `test_floor_first`: 직전 단서 사건 수가 N에 못 미치는 모양이 먼저 배정되고, 남은 예산이 실측 모양 비중대로 나뉜다.
- [ ] T015 [P] [US2] `test_cap`: 모양별 합성 ÷ 실측이 `per_shape_cap`을 넘지 않고, 초과분이 다른 모양에 재분배되며, 상한 때문에 N을 못 채운 모양이 보고에 나타난다.
- [ ] T016 [P] [US2] `test_share_warning`: 합성 비중이 `max_synthetic_share`를 넘으면 경고를 내고 오류로 멈추지 않는다. 하한 합계가 예산의 20%를 넘어도 경고한다.
- [ ] T017 [P] [US2] `test_placement`: 날짜별 에피소드 수가 일별 예산과 ±1 에피소드 안이고, 모든 시작 시각이 재료 구간 안이다.
- [ ] T018 [P] [US2] `test_reproducible`: 같은 설정·seed로 계획을 두 번 만들면 `pool_plan.jsonl`이 바이트 단위로 같다.

### 구현

- [ ] T019 [US2] `synth/pool.py`: 예산, 하한, 상한, 모양 배분(`floor_then_real_mix`, `sqrt_balance`), 날짜 배치, 에피소드 목록(합성 굴뚝 코드 `SYN-T-…`, seed, 참조 굴뚝 자리) 구현. T013~T018이 통과해야 한다.
- [ ] T020 [US2] `config/pool.yaml` 로더와 검증(필수 키, 값 범위, 구간이 외부 검증 구간(11/11 이후)을 넘지 않는지)을 만든다. 기존 `synth/plan.py`의 `load_config`를 재사용한다.
- [ ] T021 [US2] `python -m synth pool-plan`: `pool_plan.jsonl`과 요약 표(성분 × 모양 × 하한/상한/배정/미달)를 출력한다. `__main__.py`에 명령을 추가한다.
- [ ] T022 🧑 [US2] 실제 입력으로 요약 표를 확인한다: 하한 합계가 예산의 20% 이하인가, 상한 때문에 못 채운 모양은 무엇인가(SOX GRADUAL·OVER 예상), 사건당 양성 수(기본 1.85) 가정이 합리적인가.

**Checkpoint**: 데이터 없이 계획 요약 표가 나오고 규칙이 테스트로 보장된다.

---

## Phase 4: User Story 5 — 모양 곡선 (규칙 기반 + 범위 무작위화) (P3, 단계화의 1단계)

**Goal**: 모양별 범위에서 궤적을 무작위로 뽑고 모든 궤적이 의도한 모양으로 판정되게 한다. 모양 구간 생성은 나중에 교체할 수 있게 분리한다.

**Independent Test**: 모양마다 궤적 N개를 뽑아 `classify_shape`가 의도한 모양과 같다고 판정하는지 확인한다.

### 테스트 먼저

- [ ] T023 [P] [US5] `tests/test_shapes.py::test_samples_match_shape`: 모양마다 궤적 500개를 뽑아 모두 의도한 모양으로 판정된다(SC-010).
- [ ] T024 [P] [US5] `test_samples_in_range`: 값이 설정한 범위 안이고, 같은 모양에서 궤적이 서로 달라진다(고정 숫자가 아님).
- [ ] T025 [P] [US5] `test_reproducible_seed`: 같은 seed면 같은 궤적이 나온다.
- [ ] T026 [P] [US5] `tests/test_episode_assemble.py`: 에피소드(warmup + 모양 + 복귀)를 조립했을 때 길이가 설정과 같고, 모양 구간 밖의 값이 모두 90% 미만이며, 에피소드의 라벨 양성 수가 1 이상이다.

### 구현

- [ ] T027 [US5] `synth/shapes.py`에 `sample_trajectory(shape, rng, ranges)`를 구현한다. 모양 구간 생성은 함수 하나로 분리해 2단계(템플릿·파라미터 기반)가 같은 인터페이스로 교체할 수 있게 한다. T023~T025가 통과해야 한다.
- [ ] T028 [US5] `config/pool.yaml`의 `shape_ranges`를 plan의 범위 표대로 채운다.
- [ ] T029 [US5] 에피소드 조립 함수: warmup(`episode.normal_series`) + 모양 구간(`trajectory.inject` 재사용) + 복귀를 만들고, 참조 굴뚝의 평균·변동·φ와 `perm_std`를 쓴다. T026이 통과해야 한다.
- [ ] T030 🧑 [US5] 모양별 샘플 곡선을 몇 개 그려 눈으로 확인한다(너무 깨끗하거나 비현실적인지). 범위 조정이 필요하면 T028에 반영한다.

**Checkpoint**: 모든 모양의 궤적이 규칙 통과를 보장하며 범위 안에서 매번 달라진다.

---

## Phase 5: User Story 1 — 슬롯 스냅샷으로 합쳐 풀을 생성한다 (P1) 🎯 MVP

**Goal**: 에피소드들을 슬롯마다 스냅샷 하나에 합쳐 `manifest.jsonl`과 함께 파일 모드로 생성한다.

**Independent Test**: 작은 설정(에피소드 수십 개)으로 풀을 생성하고, manifest로 (성분 × 모양)별 에피소드를 집계할 수 있고 같은 seed에서 바이트가 같다.

### 테스트 먼저

- [ ] T031 [P] [US1] `tests/test_pack.py::test_one_snapshot_per_slot`: 슬롯마다 스냅샷이 하나이고, 같은 (굴뚝, 측정 시각)이 한 번만 나타난다.
- [ ] T032 [P] [US1] `test_trace_episode`: 스냅샷 항목의 굴뚝 코드로 에피소드를 되짚을 수 있고, 한 에피소드를 골라내도 그 에피소드의 모든 행이 완전하다(독립 선택).
- [ ] T033 [P] [US1] `test_snapshot_size`: 스냅샷 원문 크기가 설정한 한도(기본 1MB 미만) 안이다.
- [ ] T034 [P] [US1] `tests/test_generate_pool.py`: 풀 생성이 폴더 구조(`ingest_date=/hour=/run_ts=/`, 4개 파일)와 `manifest.jsonl` 필드(spec FR-029)를 갖추고, 같은 seed로 두 번 생성하면 바이트가 같다.
- [ ] T035 [P] [US1] `test_label_correction`: 생성 후 `label.py`로 센 실제 양성 수가 계획과 다를 때 에피소드를 추가·제거해 ±1 에피소드 안으로 맞춘다(1회 반복).

### 구현

- [ ] T036 [US1] `synth/pack.py`: 에피소드 시계열을 슬롯별 항목 목록으로 바꿔 합치고 `snapshot.make_snapshot`으로 스냅샷을 만든다. `run_ts`는 T002에서 정한 규칙을 쓴다. T031~T033이 통과해야 한다.
- [ ] T037 [US1] `synth/generate.py`에 풀 모드를 추가한다(기존 평가용 흐름은 그대로). `writer.write_files`와 `check_prefix`를 재사용하고 `tms_cleansys/` 쓰기를 거부한다. `manifest.jsonl`에 성분, 모양, 참조 굴뚝, 합성 굴뚝 코드, seed, 첫·마지막 측정 시각, 스냅샷 수, 라벨 건수, 합성 음성 수, `ref_stats_period`, 통계 버전, 생성기 버전을 기록한다. T034가 통과해야 한다.
- [ ] T038 [US1] 일별 양성 수 보정 루프(T035)를 구현한다.
- [ ] T039 [US1] `python -m synth pool-generate --config config/pool.yaml --out out`을 `__main__.py`에 추가한다.

**Checkpoint**: 풀을 파일 모드로 생성할 수 있고 manifest만으로 (성분 × 모양)별 선택이 가능하다.

---

## Phase 6: User Story 4 — 풀의 비중·시각·누출을 점검한다 (P2)

**Goal**: 풀이 규칙을 지켰는지 자동으로 확인한다.

**Independent Test**: 일부러 규칙을 어긴 풀이 각각 걸린다.

### 테스트 먼저

- [ ] T040 [P] [US4] `tests/test_validate_pool.py::test_time_outside_period`: 합성 시각이 재료 구간 밖이면 불일치로 표시한다.
- [ ] T041 [P] [US4] `test_syn_code_collision`: `SYN-` 굴뚝 코드가 실측 굴뚝 코드와 같으면 불일치로 표시한다.
- [ ] T042 [P] [US4] `test_label_mismatch`: `label.py`로 다시 센 건수가 manifest와 다르면 불일치로 표시한다.
- [ ] T043 [P] [US4] `test_stats_period_leak`: 참조 통계 구간이 외부 검증 구간(11/11 이후)을 포함하면 불일치로 표시한다.
- [ ] T044 [P] [US4] `test_share_warning_report`: 합성 비중이 `max_synthetic_share`를 넘으면 경고를 보고에 남긴다(오류 아님).
- [ ] T045 [P] [US4] `test_shape_target_report`: 모양별 목표 건수와 실제 건수를 비교해 보고한다.

### 구현

- [ ] T046 [US4] `synth/validate.py`에 `--root`(폴더 이름)와 풀 모드 세트 점검을 추가한다. 102의 점검(구조, 필드, 해시, 경로, 격자, 형식, 응답, 쌍)은 그대로 재사용한다. T040~T045가 통과해야 한다.
- [ ] T047 🧑 [US4] 실제 설정으로 풀을 생성하고 `validate`가 통과하는지, SC-001~004, SC-007~010을 확인한다. 요약 표를 plan 가정과 대조한다.

**Checkpoint**: 풀 생성 + 세트 점검이 통과하고 문제를 일부러 만든 케이스가 모두 잡힌다.

---

## Phase 7: User Story 3 — Kafka → Spark → Bronze 적재 (P1)

**Goal**: 스냅샷을 Kafka로 발행하고 Spark가 학습용 합성 전용 폴더에 파일로 적재한다. 102의 평가용 16개 에피소드로 먼저 검증하므로 Phase 2~6과 병렬로 진행할 수 있다.

**Independent Test**: 평가용 16개를 시험 모드로 발행·적재하고, 파일 모드로 직접 만든 결과와 바이트까지 같은지 비교한다.

### 환경

- [ ] T048 🧑 [US3] Docker Desktop, `sg-spark:3.5` 이미지, MinIO(`MINIO_ENDPOINT`, `MINIO_ROOT_USER`, `MINIO_ROOT_PASSWORD` 환경 변수)를 확인한다. Kafka 이미지와 클라이언트 라이브러리 버전을 확정하고 plan에 반영한다.
- [ ] T049 [P] [US3] `kafka/docker-compose.yml`(Kafka KRaft 단일 브로커, 토픽 `tms.synthetic.train` 파티션 1, 보존 기간 길게)과 `kafka/.env.example`을 만든다. 실제 `.env`는 커밋하지 않는다.
- [ ] T050 [P] [US3] `k_tms_synthetic/requirements.txt`에 Kafka 클라이언트를 추가하고 plan의 Complexity Tracking에 사유를 적는다.

### 테스트 먼저

- [ ] T051 [P] [US3] `tests/test_publish.py`: 스냅샷이 메시지(키 `run_ts`, 값 원문 바이트, 헤더에 풀 이름·생성기 버전·통계 버전)로 바뀌고, 메시지 크기가 한도를 넘으면 오류가 나는지 브로커 없이 확인한다.
- [ ] T052 [P] [US3] `tests/test_ingest_core.py`: Spark 없이 **메시지 → (경로, 파일 4개)** 변환 함수가 (a) 파일 모드 산출물과 바이트가 같고 (b) 풀 모드·시험 모드 경로 템플릿이 맞고 (c) `tms_cleansys/` 경로를 거부하고 (d) 같은 메시지에 같은 경로를 만든다(멱등)를 확인한다.

### 구현

- [ ] T053 [US3] `synth/publish.py`와 `python -m synth publish --src out --topic tms.synthetic.train`: `run_ts` 순서로 발행한다. T051이 통과해야 한다.
- [ ] T054 [US3] `ingest/spark_ingest.py`: 변환 핵심 함수(T052)를 `synth.snapshot.make_files`로 만들고, Spark(`readStream` Kafka, `trigger(availableNow=True)`, `foreachBatch`)에서 `boto3`로 데이터 파일을 먼저 저장 → 해시 검증 → `_SUCCESS` 순서로 쓴다. 체크포인트 위치를 설정한다. 경로 템플릿은 풀 모드/시험 모드를 인자로 받는다. T052가 통과해야 한다.
- [ ] T055 🧑 [US3] **시험 모드 종단 검증**: 평가용 16개(`out/`)를 발행 → 적재해 만든 폴더가 파일 모드로 만든 폴더와 바이트 단위로 같은지 비교한다(SC-005). 비교 스크립트는 `tests/integration/compare_dirs.py`에 둔다.
- [ ] T056 🧑 [US3] **멱등·재시작 검증**: 같은 토픽을 두 번 처리해도 결과가 같은지, Spark를 중간에 중단했다가 재시작해도 빠짐·중복이 없는지 확인한다(SC-006).
- [ ] T057 🧑 [US3] **풀 모드 적재**: Phase 5의 풀을 발행 → 학습용 폴더(`tms_synthetic_train/`)에 적재하고 `validate --root`가 통과하는지 확인한다.

**Checkpoint**: 풀이 Kafka → Spark → Bronze 학습용 폴더에 적재되고, 파일 모드와 바이트가 같으며, 멱등·재시작이 확인된다.

---

## Phase 8: Polish · 문서 · 협의 · PR

- [ ] T058 plan Phase 1 산출물을 작성한다: `contracts/`(학습용 폴더 구조, 메시지 형식, `manifest.jsonl` 필드, `daily_targets.csv` 형식), `data-model.md`, `quickstart.md`. plan Constitution Check IV를 통과로 바꾼다(C 협의 반영 후).
- [ ] T059 `k_tms_synthetic/README.md`에 풀 생성·발행·적재 명령을 추가한다.
- [ ] T060 🧑 E에게 **외부 검증 기간을 11/11 이후 데이터로 바꿀 수 있는지** 확인하고(합성 재료 구간 10/30~11/10과 겹치지 않게), 답으로 spec의 열린 질문을 해소해 재료 구간 설정값을 확정한다. 모양별 재현율, 클래스 가중치 등 E의 학습 설정은 이 작업의 범위가 아니다(참고로만 전달).
- [ ] T061 🧑 C에게 요청한다: 학습용 합성 폴더를 Silver·ML-ready가 읽을 수 있게 할 수 있는지(현재 읽기 경로는 `tms_cleansys/` 고정). 이 spec에서는 코드를 고치지 않는다.
- [ ] T062 🧑 **검수**: 계획 요약 표와 모양 범위를 생성자와 다른 1명이 확인한다.
- [ ] T063 `spec.md`·`plan.md`를 실제 구현 결과(사건당 양성 수, 모양 범위, Kafka·Spark 버전, 스냅샷 크기)로 갱신한다.
- [ ] T064 🧑 `git push`와 PR 생성(PR 본문에 `Closes #<새 이슈 번호>`, spec·plan·tasks와 코드를 함께, T055·T056 결과 포함).
- [ ] T065 (후속, 선택) E의 비교 실험에서 합성이 도움이 된다고 확인되면 2단계(사건 많은 모양은 실측 템플릿, 중간은 실측 파라미터 기반) 도입을 별도 작업으로 계획한다.

---

## 의존 관계와 실행 순서

- Phase 1 → Phase 2 → Phase 3 → Phase 4 → Phase 5 → Phase 6 → Phase 8 순서가 기본이다.
- **Phase 7(Kafka·Spark)은 Phase 2~6과 독립**이다(102의 평가용 16개를 재료로 쓴다). 환경 확인(T048)이 끝나면 병렬로 진행할 수 있고, T057(풀 적재)만 Phase 5 완료를 기다린다.
- 각 단계의 테스트(T009~T010, T013~T018, T023~T026, T031~T035, T040~T045, T051~T052)가 **먼저 실패하는 것을 확인한 뒤** 구현한다.
- T001~T005(🧑 쿼리)는 병렬로 진행할 수 있고, T006·T007과도 독립이다.
- Phase 4의 `shapes.py`는 Phase 2의 `classify_shape`(T012)에 의존한다. Phase 5의 `pack.py`는 Phase 4의 에피소드 조립(T029)과 T002(`run_ts` 규칙)에 의존한다.
- 병렬 가능: 같은 Phase의 [P] 테스트 파일들, T049·T050, T001~T005.

## 구현 전략

1. **MVP = Phase 1~6**: 풀을 파일 모드로 만들고 점검까지. 여기서 멈추고 검토(T022, T030, T047, T062)한다.
2. **Phase 7**은 평가용 16개로 파이프라인을 먼저 검증해 학습용 생성기와 위험을 분리한다.
3. 사람이 하는 작업(🧑)은 막히면 먼저 알린다: T001~T005(쿼리), T008(이슈·브랜치), T022·T030·T047·T062(검토), T048·T055~T057(Docker 환경), T060~T061(E·C 협의), T064(push).
4. 2단계 곡선(T065)은 E의 비교 실험 결과를 본 뒤에 결정한다.

## Notes

- 실측 경로(`tms_cleansys/`)에는 어떤 작업도 쓰지 않는다. T052·T037이 이를 테스트로 강제한다.
- 비밀값(MinIO·AWS 자격)은 코드·설정·compose·로그에 쓰지 않는다(`.env`는 커밋하지 않는다).
- `data/`와 `out/`은 커밋하지 않는다. 커밋은 작업 단위로 나눈다(`feat:`, `test:`, `docs:` + 한국어).
- 이 목록은 102의 라벨 작업(T055~T058)을 T009·T011이 대신하므로, 102 쪽에서는 해당 작업을 이 spec으로 옮긴다고 표시한다.
- 합성 규모와 모양 범위는 시작값이다. 값 조정은 설정(`pool.yaml`)에서만 하고 코드는 바꾸지 않는다.
