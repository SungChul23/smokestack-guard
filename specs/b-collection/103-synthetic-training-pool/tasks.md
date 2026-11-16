---
description: "103 K-TMS 학습용 합성 데이터 (일 단위 생성 + Kafka → Spark → Bronze 적재) 작업 목록"
---

# Tasks: K-TMS 학습용 합성 데이터 (일 단위 생성 + Kafka → Spark → Bronze 적재)

**Input**: `specs/b-collection/103-synthetic-training-pool/` (spec.md, plan.md)

**Tests**: `pytest`를 쓴다(plan). 각 단계의 구현 작업 앞에 그 단계의 테스트를 먼저 쓰고, 실패(빨간불)를 확인한 뒤 구현한다. Kafka·Spark 종단 검증은 Docker가 필요한 통합 검증으로 분리한다.

**Organization**: 사용자 스토리별 단계. **하루 단위 생성을 파일 모드로 만드는 데까지(Phase 1~5)**가 MVP이고, Kafka → Spark → Bronze 적재(Phase 6)는 102의 평가용 16개 에피소드로 먼저 검증할 수 있어 **Phase 2~5와 병렬로** 진행할 수 있다. **이 spec의 완료 범위는 Phase 1~6과 Phase 8의 최소 문서·PR(T056, T057, T060)이다.** Phase 7(Silver 연결·E 합의)은 후속으로 두며 PR 본문에 후속 과제로 적는다.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: 다른 파일이고 선행 작업이 없어 병렬 가능
- **[Story]**: US1(하루 단위 생성·backfill), US2(Kafka → Spark → Bronze 적재), US3(ML 담당자의 선택·Silver 연결), US4(점검), US5(곡선 단계화)
- 🧑 표시는 **사람이 하는 작업**(Athena·Docker 실행, 다른 담당 합의, 검수, push). 에이전트는 실행하지 않는다.

## 경로

- 새 폴더 `k_tms_synthetic_train/`(102의 `k_tms_synthetic/`은 바꾸지 않는다). 이 문서의 상대 경로는 모두 이 폴더 기준이다.
- 코드: `synth_train/`(102에서 복사한 모듈 + 신규 모듈), `ingest/`, `kafka/`
- 테스트: `tests/`, 통합 검증: `tests/integration/`
- 설정: `config/daily.yaml`
- 입력(커밋 안 함): `data/ref_stats.csv`
- 출력(커밋 안 함): `out/`

---

## Phase 1: Setup · 선행 확인

**Purpose**: plan의 가정을 확인하고 기반을 준비한다.

- [x] T001 🧑 Athena `n_snap` 분포로 실측 스냅샷 구조 확인(2026-11-05의 154,842건 모두 `n_snap = 1`, plan D1 확정).
- [x] T002 🧑 실측 `run_ts`와 `mesure_dt`의 차이 확인(94.9%가 70~79분 뒤, 합성 `run_ts` = 측정 시각 UTC + 70분, plan D14).
- [x] T003 🧑 참조 통계를 `data/ref_stats.csv`에 둔다(`stats_version = ref-1030-1110`, 3,131행, `usable` 3,062행).
- [x] T004 102의 모듈을 새 폴더로 **복사**한다(plan D15): `snapshot`, `schedule`, `writer`, `episode`, `stats`, `plan`, `scenarios/trajectory`와 테스트 9개, `tests/fixtures/ref_stats_sample.csv`. 패키지 이름 `synth_train`, `README.md`에 복사 출처 커밋(`6a6acaf`) 기록. `validate.py`는 T029에서 복사한다. `.gitignore`에 `data/`, `out/`을 추가한다.
- [x] T005 복사한 `make_files`의 **바이트 결정성**과 시각 필드가 `run_ts`를 따르는지 테스트로 확인한다(plan D11).
- [x] T006 **저장 경로의 루트와 에피소드 폴더를 선택**할 수 있게 한다(plan D12): `snapshot.build_prefix(episode_id, run_ts, root)`, `TRAIN_ROOT = "tms_synthetic_train"`, `writer.check_prefix`가 두 루트만 허용하고 `tms_cleansys/`는 계속 거부.
- [x] T007 🧑 GitHub 이슈(#50)와 브랜치를 만든다(바탕은 `29-k-tms-synthetic`).
- [ ] T008 `config/daily.yaml`을 만든다: `run`(seed, generator_version, stats_version), `snapshot`(slot_min, run_ts_offset_min, max_message_bytes), `episode`(warmup_steps, return_steps), `daily_episodes`(성분 × 모양별 하루 에피소드 수, plan 표의 시작값), `ref_selection`, `shape_ranges`(plan 범위 표), `paths`. 🧑 하루 에피소드 수의 시작값을 확인한다.

**Checkpoint**: 입력, 복사한 모듈, 경로 규칙, 설정이 있고 복사한 테스트가 모두 통과한다.

---

## Phase 2: Foundational — 라벨과 모양 판정 (모든 스토리의 전제)

**Purpose**: 생성·점검이 쓰는 모양 판정(`classify_shape`)을 먼저 만든다. 라벨 계산(`label.py`)은 Silver·ML-ready 연결 후로 미룬다(ML-ready 결과와 대조해서 만드는 것이 더 확실하다).

### 테스트 먼저

- [ ] T009 [P] **(후속: Silver·ML-ready 연결 후)** `tests/test_label.py`: 102의 `expected/*.yaml`(`trajectory_pct`, `trajectory_start_step`, `steps`, `label_expect`)을 `tests/fixtures/expected/`로 복사해 두고(출처 커밋 기록), 정상 배경(0.5 고정)에 궤적을 끼운 시계열로 `label.count_labels`의 양성·음성·제외가 `label_expect`와 모두 일치하는지 확인한다. 현재 90% 이상, 미래 값 없음, 끝 두 행 제외 경계 케이스를 별도로 테스트한다. (102의 T055~T058을 이 작업이 대신한다.)
- [ ] T010 [P] `tests/test_classify_shape.py`: 102의 고정 궤적 6개가 기대 모양으로 판정되는지 확인한다 — `[56,58,113,109,104,71,60]`→EXCEED, `[59,61,92,95,93,96,94,70,62]`→PLATEAU, `[87,91,88,92,89,91]`→OVER, `[59,61,94,63,60]`→SPIKE, `[62,69,76,82,87,92]`→GRADUAL, 해당 없음→OTHER. 판정 우선순위(EXCEED가 OVER보다 먼저)와 GRADUAL의 "직전 4값 모두 유효" 조건도 테스트한다.

### 구현

- [ ] T011 **(후속: Silver·ML-ready 연결 후)** `synth_train/label.py`: `label-v1` 규칙(현재 90% 미만, 30분 뒤 또는 60분 뒤가 90% 이상이면 양성, 둘 다 있고 90% 미만이면 음성, 현재 90% 이상이거나 미래 값을 모르면 제외, 반올림 없음)으로 건수를 센다. T009가 통과해야 한다.
- [ ] T012 `synth_train/shapes.py`에 `classify_shape`를 구현한다(사건 = 90% 이상 행을 60분 재진입으로 묶음, EXCEED → PLATEAU → OVER → SPIKE → GRADUAL → OTHER 순서). T010이 통과해야 한다.

**Checkpoint**: 고정 궤적이 올바른 모양으로 판정된다(라벨 건수 대조는 후속).

---

## Phase 3: User Story 5 — 모양 곡선 (규칙 기반 + 범위 무작위화) (P3, 단계화의 1단계)

**Goal**: 모양별 범위에서 궤적을 무작위로 뽑고 모든 궤적이 의도한 모양으로 판정되게 한다. 모양 구간 생성은 나중에 교체할 수 있게 분리한다.

**Independent Test**: 모양마다 궤적 N개를 뽑아 `classify_shape`가 의도한 모양과 같다고 판정하는지 확인한다.

### 테스트 먼저

- [ ] T013 [P] [US5] `tests/test_shapes.py::test_samples_match_shape`: 모양마다 궤적 500개를 뽑아 모두 의도한 모양으로 판정된다(SC-009).
- [ ] T014 [P] [US5] `test_samples_in_range`: 값이 설정한 범위 안이고, 같은 모양에서 궤적이 서로 달라진다(고정 숫자가 아님).
- [ ] T015 [P] [US5] `test_reproducible_seed`: 같은 seed면 같은 궤적이 나온다.
- [ ] T016 [P] [US5] `tests/test_episode_assemble.py`: 에피소드(warmup + 모양 + 복귀)를 조립했을 때 길이가 설정과 같고, 모양 구간 밖의 값이 모두 90% 미만이며, 에피소드를 `classify_shape`로 판정하면 의도한 모양이다(90%를 넘는 사건이 하나 있다).

### 구현

- [ ] T017 [US5] `synth_train/shapes.py`에 `sample_trajectory(shape, rng, ranges)`를 구현한다. 모양 구간 생성은 함수 하나로 분리해 2단계(템플릿·파라미터 기반)가 같은 인터페이스로 교체할 수 있게 한다. 샘플러가 의도와 다른 모양을 뽑으면 다시 뽑는다. T013~T015가 통과해야 한다.
- [ ] T018 [US5] `config/daily.yaml`의 `shape_ranges`를 plan의 범위 표대로 채운다.
- [ ] T019 [US5] 에피소드 조립 함수: warmup(`episode.normal_series`) + 모양 구간(`trajectory.inject` 재사용) + 복귀를 만들고, 참조 굴뚝의 평균·변동·φ와 `perm_std`를 쓴다. T016이 통과해야 한다.
- [ ] T020 🧑 [US5] 모양별 샘플 곡선을 몇 개 그려 눈으로 확인한다(너무 깨끗하거나 비현실적인지). 범위 조정이 필요하면 T018에 반영한다.

**Checkpoint**: 모든 모양의 궤적이 규칙 통과를 보장하며 범위 안에서 매번 달라진다.

---

## Phase 4: User Story 1 — 하루 단위 생성과 backfill (P1) 🎯 MVP

**Goal**: 날짜를 지정하면 그날의 스냅샷 48개(슬롯당 1개)를 만들고, 날짜 범위(backfill)는 날짜마다 독립 실행한다. 자정을 걸치는 에피소드도 저장된 상태 없이 seed로 다시 만든다.

**Independent Test**: 날짜 하나를 같은 설정으로 두 번 만들면 바이트가 같고, 날짜를 어떤 순서로 만들어도 결과가 같으며, 전날 시작해 자정을 걸친 에피소드가 두 날에 걸쳐 같은 곡선으로 이어진다.

### 테스트 먼저

- [ ] T021 [P] [US1] `tests/test_daily.py::test_episode_counts`: 날짜 하나에서 **시작하는** (성분 × 모양)별 에피소드 수가 설정과 같고, 시작 슬롯이 0~47에 퍼진다(SC-002).
- [ ] T022 [P] [US1] `test_seed_is_deterministic`: 같은 (시작 날짜, 성분, 모양, 번호)는 항상 같은 seed·참조 굴뚝·시작 슬롯이고, 다른 날짜의 에피소드와 서로 영향이 없다.
- [ ] T023 [P] [US1] `test_midnight_spill`: 자정을 걸친 에피소드를 두 날에 나눠 만들어 이으면 한 번에 만든 곡선과 같다(상태 저장 없이 seed만으로).
- [ ] T024 [P] [US1] `tests/test_pack.py::test_one_snapshot_per_slot`: 하루에 슬롯 48개마다 스냅샷 1개, 같은 (굴뚝, 측정 시각)이 한 번만 나타나고, `run_ts`가 측정 시각(UTC) + 70분이다.
- [ ] T025 [P] [US1] `test_trace_episode`: 스냅샷 항목의 굴뚝 코드(`SYN-T-…`)로 에피소드를 되짚을 수 있고, 한 에피소드를 골라내도 그 에피소드의 행이 완전하다(독립 선택, SC-004).
- [ ] T026 [P] [US1] `test_snapshot_size`: 스냅샷 원문 크기가 설정한 한도(기본 1MB 미만) 안이다(SC-003).
- [ ] T027 [P] [US1] `tests/test_generate.py`: 하루 생성이 폴더 구조(`ingest_date=/hour=/run_ts=/`, 4개 파일)와 manifest 필드(spec FR-027)를 갖추고, (가) 같은 날짜를 두 번 만들면 바이트가 같고 (나) 두 날짜를 어떤 순서로 만들어도 결과가 같고 (다) 합성 양성이 24시간 시간대에 걸쳐 분포한다(SC-001, SC-002).

### 구현

- [ ] T028 [US1] `synth_train/daily.py`: 하루 에피소드 목록, 에피소드 seed(`f(설정 seed, 시작 날짜, 성분, 모양, 번호)`), 시작 슬롯, 합성 굴뚝 코드(`SYN-T-<날짜>-<성분>-<모양>-<번호>`), 전날 시작분 재생성. T021~T023이 통과해야 한다.
- [ ] T029 [US1] `synth_train/pack.py`: 에피소드 시계열을 슬롯별 항목 목록으로 바꿔 합치고 `snapshot.make_snapshot`으로 스냅샷을 만든다. `run_ts`는 측정 시각(UTC) + 70분. T024~T026이 통과해야 한다.
- [ ] T030 [US1] `synth_train/generate.py`: `generate_day(date)`와 `backfill(start, end)`를 구현한다. 복사한 `writer.write_files`와 `check_prefix`를 재사용하고 `tms_cleansys/` 쓰기를 거부한다. `manifest.jsonl`(하루 단위 파일, 시작 날짜가 그날인 에피소드만)에 날짜, 성분, 모양, 참조 굴뚝, 합성 굴뚝 코드, seed, 첫·마지막 측정 시각, 스냅샷 수, 행 수, 통계 버전, 생성기 버전을 기록한다(라벨 건수·합성 음성 수는 `label.py`가 생긴 뒤에 추가). T027이 통과해야 한다.
- [ ] T031 [US1] `python -m synth_train generate-day --date YYYY-MM-DD --config config/daily.yaml --out out`과 `backfill --from YYYY-MM-DD --to YYYY-MM-DD`를 `__main__.py`에 추가한다.
- [ ] T032 🧑 [US1] 실제 설정으로 하루를 만들어 확인한다: 스냅샷 48개, 행 수(약 6,600), 스냅샷당 크기(약 80KB), 합성 양성의 시간대 분포(양성 수는 ML-ready 이후 하루 NOX 약 403, SOX 약 103과 비교). 어긋나면 `daily.yaml`의 에피소드 수만 조정한다.

**Checkpoint**: 하루 단위 생성과 backfill이 파일 모드로 되고, 같은 날짜는 같은 결과이며 날짜 순서와 무관하다.

---

## Phase 5: User Story 4 — 생성 결과를 점검한다 (P2)

**Goal**: 생성된 합성 데이터가 규칙을 지켰는지 자동으로 확인한다.

**Independent Test**: 일부러 규칙을 어긴 출력이 각각 걸린다.

### 테스트 먼저

- [ ] T033 [P] [US4] `tests/test_validate.py::test_syn_code_collision`: `SYN-` 굴뚝 코드가 실측 굴뚝 코드와 같으면 불일치로 표시한다.
- [ ] T034 [P] [US4] `test_day_slots`: 하루치 스냅샷의 측정 시각이 지정한 날짜(KST)가 아니거나 슬롯이 48개가 아니면 불일치로 표시한다.
- [ ] T035 [P] [US4] **(후속: `label.py` 이후)** `test_label_mismatch`: `label.py`로 다시 센 건수가 manifest와 다르면 불일치로 표시한다.
- [ ] T036 [P] [US4] `test_shape_mismatch`: 곡선이 `classify_shape`로 판정했을 때 의도한 모양과 다르면 불일치로 표시한다.
- [ ] T037 [P] [US4] `test_spill_continuity`: 자정을 걸친 에피소드의 두 날 데이터가 이어지지 않으면 불일치로 표시한다.
- [ ] T038 [P] [US4] `test_no_defects`: 값에 숫자가 아닌 문자열·결측 구조·중복이 있으면 불일치로 표시한다(SC-010).

### 구현

- [ ] T039 [US4] 102의 `validate.py`를 복사하되 평가용 `compare` import와 `expected_dir` 대조를 뺀 `synth_train/validate.py`에 `--root`(폴더 이름)와 세트 점검(T033~T038)을 추가한다. 102의 점검(구조, 필드, 해시, 경로, 격자, 형식, 응답, 쌍)은 그대로 재사용한다. T033~T038이 통과해야 한다.
- [ ] T040 [US4] `python -m synth_train summary --manifest-dir out/manifest`: (날짜 × 성분 × 모양)별 에피소드 수와 양성 수를 집계해 출력한다(E가 선택하기 전에 보는 요약, SC-004).
- [ ] T041 🧑 [US4] 실제 설정으로 backfill 범위를 만들고 `validate`가 통과하는지, `summary`가 설정과 맞는지 확인한다(SC-001~004, 007~010).

**Checkpoint**: 생성 + 점검이 통과하고, 문제를 일부러 만든 케이스가 모두 잡힌다.

---

## Phase 6: User Story 2 — Kafka → Spark → Bronze 적재 (P1)

**Goal**: 스냅샷을 Kafka로 발행(과거는 배치, 지금부터는 `release`로 `run_ts` 시각에 하나씩)하고 Spark가 학습용 합성 전용 폴더에 파일로 적재한다. 102의 평가용 16개 에피소드로 먼저 검증하므로 Phase 2~5와 병렬로 진행할 수 있다.

**Independent Test**: 평가용 16개를 시험 모드로 발행·적재하고, 파일 모드로 직접 만든 결과와 바이트까지 같은지 비교한다.

### 환경

- [ ] T042 🧑 [US2] Docker Desktop, `sg-spark:3.5` 이미지, MinIO(`MINIO_ENDPOINT`, `MINIO_ROOT_USER`, `MINIO_ROOT_PASSWORD` 환경 변수)를 확인한다. Kafka 이미지와 클라이언트 라이브러리 버전을 확정하고 plan에 반영한다.
- [ ] T043 [P] [US2] `kafka/docker-compose.yml`(Kafka KRaft 단일 브로커, 토픽 `tms.synthetic.train` 파티션 1, 보존 기간 길게)과 `kafka/.env.example`을 만든다. 실제 `.env`는 커밋하지 않는다.
- [ ] T044 [P] [US2] `requirements.txt`에 Kafka 클라이언트를 추가하고 plan의 Complexity Tracking에 사유를 적는다.

### 테스트 먼저

- [ ] T045 [P] [US2] `tests/test_publish.py`: 스냅샷이 메시지(키 `run_ts`, 값 원문 바이트, 헤더에 생성기 버전·통계 버전)로 바뀌고, 메시지 크기가 한도를 넘으면 오류가 나는지 브로커 없이 확인한다.
- [ ] T045b [P] [US2] `tests/test_release.py`(시계를 인자로 주입, 브로커 없이 발행 호출을 기록하는 가짜 발행자로): (a) `run_ts`가 지금 이전인 스냅샷만 발행되고 이후 것은 발행되지 않는다, (b) 같은 시각에 두 번 실행해도 결과가 같다(멱등), (c) 실행을 건너뛴 뒤 다시 실행하면 밀린 것이 모두 올라간다, (d) 오늘·내일 하루치가 없으면 먼저 생성한다(SC-012).
- [ ] T046 [P] [US2] `tests/test_ingest_core.py`: Spark 없이 **메시지 → (경로, 파일 4개)** 변환 함수가 (a) 파일 모드 산출물과 바이트가 같고 (b) 풀 모드·시험 모드 경로 템플릿이 맞고 (c) `tms_cleansys/` 경로를 거부하고 (d) 같은 메시지에 같은 경로를 만든다(멱등)를 확인한다.

### 구현

- [ ] T047 [US2] `synth_train/publish.py`와 `python -m synth_train publish --src out --topic tms.synthetic.train`: `run_ts` 순서로 **하루치를 한꺼번에** 발행한다(배치, backfill용). T045가 통과해야 한다.
- [ ] T047b [US2] `synth_train/release.py`와 `python -m synth_train release --config config/daily.yaml [--now ISO시각]`: 오늘·내일 하루치가 없으면 생성하고, `run_ts`가 현재 시각 이전인 스냅샷만 발행한다(멱등, 올린 기록을 상태로 두지 않음). 마지막 발행 `run_ts`를 로그에 남긴다. T045b가 통과해야 한다.
- [ ] T048 [US2] `ingest/spark_ingest.py`: 변환 핵심 함수(T046)를 `synth_train.snapshot.make_files`로 만들고, Spark(`readStream` Kafka, `trigger(availableNow=True)`, `foreachBatch`)에서 `boto3`로 데이터 파일을 먼저 저장 → 해시 검증 → `_SUCCESS` 순서로 쓴다. 체크포인트 위치를 설정한다. 경로 템플릿은 풀 모드/시험 모드를 인자로 받는다. T046이 통과해야 한다.
- [ ] T049 🧑 [US2] **시험 모드 종단 검증**: 평가용 16개(같은 브랜치의 `k_tms_synthetic/`에서 `python -m synth generate`로 만든 `out/`)를 발행 → 적재해 만든 폴더가 파일 모드로 만든 폴더와 바이트 단위로 같은지 비교한다(SC-005). 비교 스크립트는 `tests/integration/compare_dirs.py`에 둔다.
- [ ] T050 🧑 [US2] **멱등·재시작 검증**: 같은 토픽을 두 번 처리해도 결과가 같은지, Spark를 중간에 중단했다가 재시작해도 빠짐·중복이 없는지 확인한다(SC-006).
- [ ] T051 🧑 [US2] **학습용 적재(backfill)**: 10/30~어제의 하루치를 발행 → 학습용 폴더(`tms_synthetic_train/`)에 적재하고 `validate --root`가 통과하는지 확인한다(SC-011).
- [ ] T051b 🧑 [US2] **방출 확인**: 몇 시간 동안 10분 간격으로 `release`를 실행(직접 또는 스케줄러)해, 각 슬롯의 스냅샷이 자기 `run_ts` 직후 실행에서 Bronze에 생기는지, 실행을 건너뛴 뒤 따라잡는지 확인한다(SC-012). 스케줄러 구성은 후속이며 확인은 직접 반복 실행으로 해도 된다.

**Checkpoint**: 합성 데이터가 Kafka → Spark → Bronze 학습용 폴더에 적재되고, 파일 모드와 바이트가 같으며, 멱등·재시작이 확인된다.

---

## Phase 7: User Story 3 — ML 담당자의 선택과 Silver 연결 (P1) — **후속, 이 spec의 완료 조건 밖**

**Goal**: 합성 데이터가 Silver → ML-ready로 흘러 ML 담당자가 골라 쓸 수 있게 한다.

- [ ] T052 🧑 [US3] C에게 요청한다: 학습용 합성 폴더(`tms_synthetic_train/`)를 Silver·ML-ready가 읽을 수 있는지(현재 K-TMS Silver의 읽기 경로는 `tms_cleansys/` 고정). 이 spec에서는 코드를 고치지 않고 요청과 협의 결과를 기록한다. **합성이 ML에 쓰이려면 필요한 핵심 경로**다.
- [ ] T053 🧑 [US3] E와 확인한다: (1) 검증·평가 데이터에서 `SYN-` 굴뚝 코드(또는 합성 경로)를 제외할 수 있는지, (2) 외부 검증을 11/11 이후 데이터로 바꿀 수 있는지(참조 통계 기간 10/30~11/10과 겹치지 않게). 모양별 재현율, 클래스 가중치 등 E의 학습 설정은 이 작업의 범위가 아니다(참고로 전달).
- [ ] T054 [US3] `manifest.jsonl` 태그로 (날짜 × 성분 × 모양) 선택이 가능한지, 골라낸 에피소드가 독립적으로 쓰이는지를 `summary`와 `tests`로 확인한다(T025, T040 재사용).
- [ ] T055 🧑 [US3] ML-ready까지 한 번 흘려 보고(작은 날짜 범위), 라벨 양성 수가 manifest의 `label_counts`와 맞는지 확인한다(C·E와 함께).

**Checkpoint**: Silver·ML-ready 경로와 합성 제외 규칙이 합의되고, 합성 데이터가 ML-ready에서 라벨 건수가 맞게 보인다.

---

## Phase 8: Polish · 문서 · PR

- [ ] T056 plan Phase 8 산출물을 작성한다: `contracts/`(학습용 폴더 구조, 메시지 형식, `manifest.jsonl` 필드), `data-model.md`(설정 필드, 하루 생성량), `quickstart.md`(생성·backfill·발행·적재 순서). plan Constitution Check IV를 통과로 바꾼다(C 협의 반영 후).
- [ ] T057 `k_tms_synthetic_train/README.md`에 하루 생성, backfill, 배치 발행, 방출(`release`, 10분 주기 실행 예시: Windows 작업 스케줄러·cron), 적재 명령과 복사 출처를 정리한다.
- [ ] T058 🧑 **검수**: 하루 에피소드 수 설정과 모양 범위를 생성자와 다른 1명이 확인한다.
- [ ] T059 `spec.md`·`plan.md`를 실제 구현 결과(사건당 양성 수, 모양 범위, 하루 에피소드 수, Kafka·Spark 버전, 스냅샷 크기)로 갱신한다.
- [ ] T060 🧑 `git push`와 PR 생성(PR 본문에 `Closes #50`, spec·plan·tasks와 코드를 함께, T049·T050 결과 포함). 기준 브랜치는 #29(`29-k-tms-synthetic`)이며, #29가 `main`에 머지되면 `main`으로 바꾼다.
- [ ] T061 (후속, 선택) 스케줄러 구성(Windows 작업 스케줄러, cron, Airflow), 2단계 곡선(사건 많은 모양은 실측 템플릿, 중간은 실측 파라미터 기반)은 필요가 확인되면 별도 작업으로 계획한다.

---

## 의존 관계와 실행 순서

- Phase 1 → Phase 2 → Phase 3 → Phase 4 → Phase 5 → Phase 7 → Phase 8 순서가 기본이다.
- **Phase 6(Kafka·Spark)은 Phase 2~5와 독립**이다(102의 평가용 16개를 재료로 쓴다). 환경 확인(T042)이 끝나면 병렬로 진행할 수 있고, T051(학습용 적재)만 Phase 4 완료를 기다린다.
- 각 단계의 테스트(T009~T010, T013~T016, T021~T027, T033~T038, T045~T046)가 **먼저 실패하는 것을 확인한 뒤** 구현한다.
- Phase 3의 `shapes.py`는 Phase 2의 `classify_shape`(T012)에 의존한다. Phase 4의 `daily.py`는 Phase 3의 에피소드 조립(T019)에, `pack.py`는 `run_ts` 규칙(T002)에 의존한다.
- T052(C 협의), T053(E 확인)은 **지금 시작해도 되는 사람 작업**이다(코드와 독립).
- 병렬 가능: 같은 Phase의 [P] 테스트 파일들, T043·T044, T052·T053.

## 구현 전략

1. **MVP = Phase 1~5**: 하루 단위 생성과 backfill을 파일 모드로 만들고 점검까지. 여기서 멈추고 검토(T020, T032, T041, T058)한다.
2. **Phase 6**은 평가용 16개로 파이프라인을 먼저 검증해 학습용 생성기와 위험을 분리한다.
3. 사람이 하는 작업(🧑)은 막히면 먼저 알린다: T007(이슈, 완료), T008(시작값 확인), T020·T032·T041·T058(검토), T042·T049~T051(Docker 환경), T052·T053·T055(C·E 협의), T060(push).
4. 방출 방식·스케줄링·2단계 곡선(T061)은 필요가 확인된 뒤에 결정한다.

## Notes

- 실측 경로(`tms_cleansys/`)에는 어떤 작업도 쓰지 않는다. T006(완료)·T046이 이를 테스트로 강제한다.
- 비밀값(MinIO·AWS 자격)은 코드·설정·compose·로그에 쓰지 않는다(`.env`는 커밋하지 않는다).
- `data/`와 `out/`은 커밋하지 않는다. 커밋은 작업 단위로 나눈다(`feat:`, `test:`, `docs:` + 한국어).
- 이 목록은 102의 라벨 작업(T055~T058)을 T009·T011이 대신하므로, 102 쪽에서는 해당 작업을 이 spec으로 옮긴다고 표시한다.
- 코드는 새 폴더 `k_tms_synthetic_train/`에서만 작업하고 102의 `k_tms_synthetic/`은 바꾸지 않는다(복사 출처 커밋을 README에 남긴다). PR 기준 브랜치는 #29(`29-k-tms-synthetic`)이며, #29가 `main`에 머지되면 기준을 `main`으로 바꾼다.
- 하루 생성량(1:1), 모양 범위는 시작값이다. 값 조정은 설정(`config/daily.yaml`)에서만 하고 코드는 바꾸지 않는다.
- 합성이 ML로 쓰이려면 C의 Silver 읽기 경로 변경(T052)과 E의 합성 제외 규칙(T053)이 필요하다. 코드와 독립이라 먼저 시작할 수 있다.
