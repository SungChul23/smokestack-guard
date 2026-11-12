---
description: "102 K-TMS 합성 데이터 생성기 (평가·시연용) 작업 목록"
---

# Tasks: K-TMS 합성 데이터 생성기 (평가·시연용)

**Input**: `specs/b-collection/102-synthetic-generator/` (plan.md, spec.md, data-model.md, contracts/, quickstart.md)

**Tests**: pytest를 쓴다(plan). 각 단계의 구현 작업 앞에 그 단계의 테스트를 먼저 쓰고, 실패를 확인한 뒤 구현한다.

**Organization**: 사용자 스토리별 단계. 스토리 1(S-01~S-04)이 MVP이며, 한 단계씩 끝내고 다음으로 간다(구현 순서 ②→③→④).

## Format: `[ID] [P?] [Story] Description`

- **[P]**: 다른 파일이고 선행 작업이 없어 병렬 가능
- **[Story]**: US1(판정 경계·시간 패턴), US2(데이터 품질), US3(전달), US4(기대 결과 대조), US5(재현성)
- 🧑 표시는 **사람이 하는 작업**(AWS·Athena 실행, 다른 담당 합의, 검수, push). 에이전트는 실행하지 않는다.

## 경로

- 코드: `k_tms_synthetic/synth/`, 테스트: `k_tms_synthetic/tests/`
- 설정·기대 결과: `k_tms_synthetic/config/`, `k_tms_synthetic/expected/`
- 입력: `k_tms_synthetic/data/ref_stats.csv` (커밋 안 함), 출력: `k_tms_synthetic/out/` (커밋 안 함)

---

## Phase 1: Setup (구현 순서 ①)

**Purpose**: 폴더, 의존성, 입력 통계를 준비한다.

- [ ] T001 `k_tms_synthetic/` 폴더 구조를 만든다: `synth/`, `synth/scenarios/`, `tests/`, `config/`, `expected/`, `README.md`(한 줄 설명과 [quickstart](quickstart.md) 링크). 각 패키지에 `__init__.py`.
- [ ] T002 [P] `k_tms_synthetic/requirements.txt`에 `pyyaml`(+ 버전 하한)을 적는다. 저장소 기존 의존성(`pandas`, `boto3`)은 다시 적지 않는다.
- [ ] T003 [P] `.gitignore`에 `k_tms_synthetic/out/`, `k_tms_synthetic/data/`를 추가한다 (루트 `.gitignore`는 이 브랜치에서 이미 로그·샘플을 추가함. 합성 줄만 더한다).
- [ ] T004 🧑 `.github/CODEOWNERS`에 `/k_tms_synthetic/  @olchangiagi @SungChul23` 한 줄을 추가한다 (AGENTS.md: 새 작업 폴더는 담당자가 추가).
- [ ] T005 🧑 Athena에서 통계 쿼리 B를 실행해 CSV를 받고 `k_tms_synthetic/data/ref_stats.csv`로 둔다. 컬럼은 [data-model.md](data-model.md) 입력 표와 같아야 한다. (2026-11-09에 받은 CSV로 시작 가능)
- [ ] T006 `config/config.yaml`을 [data-model.md](data-model.md)의 예시대로 만든다(에피소드 21개와 시나리오별 변형·성분, seed, 참조 조건(정상 `p99_max` 70, S-03 100), `start_kst`).

**Checkpoint**: 입력과 설정이 있고, 빈 패키지를 import할 수 있다.

---

## Phase 2: Foundational — 공통 부품 (모든 스토리의 전제)

**Purpose**: 스냅샷을 만들고, 쓰고, 다시 읽어 점검하는 뼈대. **이 단계가 끝나기 전에는 스토리 작업을 시작하지 않는다.**

### 테스트 먼저

- [ ] T007 [P] `tests/test_stats.py`: `ref_stats.csv`를 읽어 후보를 거르는 규칙(유효 값 ≥200, std>0, 허용기준 1종)이 spec FR-008의 숫자와 같은지 (2,985개 사용 가능). 작은 샘플 CSV를 `tests/fixtures/`에 둔다.
- [ ] T008 [P] `tests/test_episode.py`: AR(1) 통계 복원(평균·표준편차·φ), 거부 샘플링이 상한(`hi`, 기본 시나리오별 70·100%) 미만만 내는지(값을 자르지 않음), 재시도 상한 초과 시 실패, **궤적 앞 구간이 첫 값 근처에서 끝나고 뒤 구간이 마지막 값에서 평균으로 돌아오는지**.
- [ ] T009 [P] `tests/test_snapshot.py`: 직렬화 형식(18필드 문자열, 측정값 소수 둘째 자리, 허용기준 정수, 재지 않는 항목은 null, 항목 밖 필드 없음), 응답 헤더(`resultCode "0"`, `totalCount` = 항목 수), 폴더 규칙(`episode=`/`ingest_date`/`hour`/`run_ts`).
- [ ] T010 [P] `tests/test_writer.py`: `tms_cleansys/` 아래 경로를 쓰려 하면 **거부**하는지(원칙 I), 같은 입력이면 gzip 바이트가 같은지(`mtime=0`).

### 구현

- [ ] T011 `synth/stats.py`: `ref_stats.csv` 읽기, 후보 거르기, 시나리오별 조건(`normal`, `trajectory`의 `default`·`S-03`) 적용, seed로 무작위 선택. NOX+SOX 에피소드용으로 같은 굴뚝의 NOX·SOX 쌍을 고르는 `pick_pair` 포함. (T007)
- [ ] T012 `synth/episode.py`: AR(1) 곡선 생성(하한 0), 거부 샘플링, 시간 역방향·정방향 궤적 이어 붙이기. 에피소드별 `SeedSequence`로 난수 분리. (T008)
- [ ] T013 [P] `synth/schedule.py`: 10분 간격 `run_ts`, 30분 격자 `mesure_dt`, 각 스냅샷이 담는 최신 측정값 결정(합성은 기본 지연 0).
- [ ] T014 `synth/snapshot.py`: 항목 직렬화, 스냅샷 원문·메타·`manifest.json`·`_SUCCESS` 만들기. 메타에 `synthetic`(에피소드·시나리오·생성기·통계 버전) 포함. (T009)
- [ ] T015 `synth/writer.py`: 로컬 쓰기(합성 경로만 허용, 실측 경로 거부). (T010)
- [ ] T016 `synth/plan.py`: 설정 → 에피소드 계획(에피소드 ID, 합성 배출구 코드 `SYN-…`, 성분, 오르는 성분 `rising`, 참조, seed, 시작 시각). 변형 × 성분을 펼친다(S-03·S-04). 에피소드 ID 규칙(`S-02-E-NOXSOX-NOXUP`, `S-03-E-OVER-SOX` 등)은 [contracts](contracts/synthetic-layout.md)와 같게.
- [ ] T017 `synth/__main__.py`: `generate` 명령(설정 → 계획 → 곡선 → 스냅샷 → 쓰기, `manifest.jsonl` 기록). `validate`는 뼈대만.
- [ ] T018 `synth/validate.py` 핵심: 생성된 **파일을 다시 읽어**(메모리 값 공유 금지) 구조·필드·경로·`SYN-`·30분 격자·문자열 형식·응답 점검을 검사한다. 합격 기준 1~7 ([data-model.md](data-model.md) 검증 규칙).

**Checkpoint**: 정상 시계열로 스냅샷을 만들고 쓰고 다시 읽어 점검할 수 있다. 실측 경로 쓰기는 거부된다.

---

## Phase 3: User Story 1 — 판정 경계와 시간 패턴 시나리오 (P1) 🎯 MVP (구현 순서 ②③)

**Goal**: S-01~S-04의 에피소드 16개를 설계한 궤적 그대로 만든다.

**Independent Test**: 16개를 생성해 `validate`가 궤적과 기대 결과 대조, `to_silver` 읽기에 통과한다.

### 기대 결과를 먼저 쓴다 (spec FR-017)

- [ ] T019 [P] [US1] `expected/S-01-E-NOX.yaml`, `S-01-E-SOX.yaml`: 전 행 정상 단계(ratio < 0.7), `status=ok`.
- [ ] T020 [P] [US1] `expected/S-02-E-NOX.yaml`, `S-02-E-SOX.yaml`, `S-02-E-NOXSOX-NOXUP.yaml`, `S-02-E-NOXSOX-SOXUP.yaml`: 궤적 62·69·76·82·87·92(정상→정상→주의→경고→경고→위험), `silver_expect`(오르는 성분의 6개 값 ratio 보존, NOXSOX는 다른 성분이 정상 배경), `later_expect`(6번째 위험, 4·5번째 양성, 사전 경고).
- [ ] T021 [P] [US1] `expected/S-03-E-{OVER,UNDER}-{NOX,SOX}.yaml`(OVER 87·91·88·92·89·91, UNDER 76·84·79·88·81·87·78 예시), `S-04-E-{EXCEED,SPIKE,PLATEAU}-{NOX,SOX}.yaml`(EXCEED 56·58·113·109·104·71·60, SPIKE 59·61·94·63·60, PLATEAU 59·61·92·95·93·96·94·70·62 예시). 변형 하나의 궤적은 NOX·SOX가 공유하고 `items`만 다르다. 궤적 앞 구간의 라벨 영향(S-03은 앞 구간도 주의·경고 수준)을 함께 적는다. 경고 이력 칸은 "경고 판정 단계에서 정함".
- [ ] T022 🧑 [US1] 위 expected 파일을 **생성기를 만든 사람과 다른 1명이 검수**한다 (생성 전에).

### 테스트 먼저

- [ ] T023 [P] [US1] `tests/test_trajectory.py`: 궤적 값 순서·개수가 정확하고, 앞뒤 구간이 시나리오 상한(S-01·S-02·S-04 70%, S-03 100%) 이내이며, S-02에서 6번째 값에서 처음 90% 이상, S-04 `SPIKE`에서 한 값만 90% 이상인지. NOXSOX 에피소드에서 오르지 않는 성분이 정상 배경인지.
- [ ] T024 [P] [US1] `tests/test_silver_integration.py`: 생성 결과를 `to_silver`(저장소 `src/smokestack_guard/silver/ktms.py`, `PYTHONPATH=../src`)에 통과시켜 행 수·`status`·ratio가 expected와 같은지. S3 없이 파일을 읽어 DataFrame으로 만든다.

### 구현

- [ ] T025 [US1] `synth/scenarios/trajectory.py`: S-02~S-04 주입 함수 `inject(r, rng, params) -> (r', meta)`. params에 오르는 성분 `rising`을 받는다. 참조 조건에 `|첫 값 − 평균| ≤ 2σ` 반영(조건에 맞는 후보가 적으면 배수 조정, 근거를 research 메모로 남김). 시나리오별 상한(`p99_max`·`hi`)은 설정에서 받는다. (T023)
- [ ] T026 [US1] S-01 정상 기준선 에피소드(NOX, SOX) 계획과 생성(`plan.py`, `episode.py` 연결, `hi` 70). (T019)
- [ ] T027 [US1] `synth/validate.py`에 **expected 대조**를 추가한다: `trajectory_pct`와 `silver_expect`를 읽어 비교, 불일치 목록 출력. 합격 기준 8·9(S-01 통계 ±10%/±0.1)도 구현. (T024)
- [ ] T028 [US1] 에피소드 16개를 `generate`로 만들고 `validate`를 통과시킨다. (SC-001, SC-002)

**Checkpoint**: S-01~S-04가 기대 결과와 일치하고 현재 Silver가 읽는다. 여기서 한 번 멈추고 검토한다.

---

## Phase 4: User Story 2 — 데이터 품질 시나리오 (P1) (구현 순서 ④-1)

**Goal**: 문자열 값(S-05)과 구조가 깨진 데이터(S-06)를 만든다.

**Independent Test**: S-05·S-06을 생성해 문구 5종·콤마 숫자·결함이 설계대로 들어 있고, 알려진 Silver 불일치가 점검에 표시된다.

- [ ] T029 [P] [US2] `expected/S-05-E.yaml`: 85측정의 구성(문구 5종의 구간 길이와 실측 비중 순서, 숫자 → 문구 → 숫자 전환 위치, 콤마 숫자 2개 위치), 문구 → `status` 코드, 콤마 숫자는 `known_mismatch`(현재 Silver는 `other`, 기대는 숫자 파싱).
- [ ] T030 [P] [US2] `expected/S-06-E.yaml`: 항목 단위(필수 필드 누락, 타입 이상)와 파일 단위(잘린 JSON) 결함 위치, Silver 기대(`dropna` 제외 등), 잘린 JSON 시험 방식(파일 단위 JSON 오류 확인).
- [ ] T031 🧑 [US2] 두 expected 파일을 다른 1명이 검수한다.
- [ ] T032 [P] [US2] `tests/test_strings_defects.py`: 문구 5종이 원문 그대로, 콤마 숫자가 값 1,000 이상 문자열 `"1,047.55"` 형태, 숫자 → 문구 → 숫자 전환이 있는지, S-06 결함이 별도 에피소드 폴더에 있고 정상 에피소드는 영향받지 않는지.
- [ ] T033 [US2] `synth/scenarios/strings.py`: 상태 문구 구간(실측 지속 분포 1~6스텝, 문구 비중은 가동중지 > 미수신 > 기기점검 > 보수중 > 확인중)과 콤마 숫자(극단 초과값 400~1,000% 이상, 콤마 표기). (T032)
- [ ] T034 [US2] `synth/disturb.py` 결함부: 항목 결함 주입, 파일 결함(잘린 JSON) 생성. 결함은 S-06 에피소드 폴더에만. (T032)
- [ ] T035 [US2] `validate`가 S-06 폴더를 **파일 단위로** 검사(정상 에피소드와 분리)하고, S-05 콤마 숫자를 `known_mismatch`로 보고하도록 한다.
- [ ] T036 [US2] S-05·S-06 생성 후 `validate` 통과(알려진 불일치는 표시만).

**Checkpoint**: 품질 시나리오가 생성되고, 깨진 파일이 다른 에피소드 읽기를 막지 않는다.

---

## Phase 5: User Story 3 — 전달 시나리오 (P1) (구현 순서 ④-2)

**Goal**: 중복·충돌(S-07)과 지연·누락(S-08)을 만든다.

**Independent Test**: S-07·S-08을 생성해 `delivery.jsonl`의 중복·충돌·지연·누락이 설계값과 같고, Silver가 중복 제거·시간순 정렬을 올바르게 한다.

- [ ] T037 [P] [US3] `expected/S-07-E-SAME.yaml`: 변형 A(같은 스냅샷 2행)·B(여러 스냅샷 반복)·C(위험 94% 재등장), Silver 기대 `(배출구, 측정 시각, 항목)`당 1행. `expected/S-07-E-CONFLICT.yaml`: 같은 측정에 다른 값, 계획서 기대는 "격리", 현재 Silver는 가장 늦은 스냅샷 유지 → `known_mismatch`.
- [ ] T038 [P] [US3] `expected/S-08-E.yaml`: 30분·60분·90분 지연 값, 순서 뒤바뀜, 끝내 나타나지 않는 값(누락), Silver 기대(워터마크 없음 → 지연 값은 모두 포함·시간순·중복 키 유지, 누락은 행 없음). 이후 기대에 "격리 규칙이 생기면 90분 값 격리".
- [ ] T039 🧑 [US3] 세 expected 파일을 다른 1명이 검수한다.
- [ ] T040 [P] [US3] `tests/test_delivery.py`: 변형별 중복 행 수, 재등장 값이 원래 값과 같은지, 충돌 값이 서로 다른지, 지연 분(30·60·90)과 순서 뒤바뀜, 누락 위치, 실측 기본 지연(70분)을 만들지 않는지.
- [ ] T041 [US3] `synth/disturb.py` 전달부: 중복·충돌·지연·누락 주입과 `delivery.jsonl`(`delay_min`, `duplicate_of`) 기록. (T040)
- [ ] T042 [US3] `synth/schedule.py`가 지연·중복·누락을 반영해 스냅샷 구성(어느 스냅샷에 값이 처음 나타나는지)을 결정하도록 한다.
- [ ] T043 [US3] S-07·S-08을 생성하고 `to_silver` 대조까지 `validate` 통과.

**Checkpoint**: 에피소드 21개가 모두 생성되고 점검을 통과한다(알려진 불일치 표시 포함).

---

## Phase 6: User Story 4 — 기대 결과 대조와 수동 검수 (P1)

**Goal**: 기대 결과 선작성, 자동 대조, 다른 사람의 수동 대조를 마무리한다. (자동 대조는 T027·T035에서 이미 구현. 여기서는 전체를 묶는다.)

- [ ] T044 [US4] `validate`가 에피소드 21개 전체를 한 번에 점검하고 시나리오별 통과/불일치 표를 출력하게 한다. 알려진 불일치는 별도 구분.
- [ ] T045 🧑 [US4] 생성자와 다른 1명이 `expected/`와 `out/`을 수동으로 대조한다. 결과(불일치 없음 또는 목록)를 PR 설명에 적는다. (SC-005)
- [ ] T046 [US4] `expected/`가 **생성 커밋보다 먼저 커밋**되었는지 확인하는 방법을 README에 적는다(커밋 순서로 확인).
- [ ] T055 [P] [US4] `tests/test_label.py`: `label-v1` 고정 사례(t+30만 ≥ 0.90, t+60만 ≥ 0.90, 한쪽 결측, 상태 문구, 현재 이미 90% 이상, 재진입 사건 묶음, 정확히 90%). (FR-019)
- [ ] T056 [US4] `synth/label.py`: 생성한 값에서 양성·음성·제외를 계산한다(파일에는 쓰지 않음). `validate`가 expected의 라벨 열과 교차 확인한다. (T055)
- [ ] T057 [US4] `generate`가 시나리오별 양성·음성·제외 건수를 출력하고 `manifest.jsonl`에 기록한다. (FR-020)
- [ ] T058 🧑 [US4] E와 `label-v1` 규칙, expected의 라벨 열을 대조한다.

---

## Phase 7: User Story 5 — 재현성 (P2)

**Goal**: 같은 설정이면 같은 결과가 나온다.

- [ ] T047 [P] [US5] `tests/test_reproducibility.py`: 같은 `config.yaml`로 두 번 생성해 모든 파일의 해시가 같은지. 에피소드 하나를 설정에서 빼도 다른 에피소드 결과가 변하지 않는지.
- [ ] T048 [US5] `manifest.jsonl`·메타에 `generator_version`, `stats_version`, `seed`가 모두 기록되는지 확인하고 빠진 것을 채운다. (T047)

---

## Phase 8: Polish & 후속 (구현 순서 ⑤⑥)

- [ ] T049 [P] `k_tms_synthetic/README.md`를 [quickstart.md](quickstart.md) 기준으로 채우고, 명령 이름이 확정되면 quickstart의 "구현 전" 문구를 지운다.
- [ ] T050 [P] `synth upload` 명령: 합성 경로에만 업로드(실측 경로 거부), MinIO·S3 자격은 환경 변수. 업로드는 사람이 실행. (원칙 I·II)
- [ ] T051 🧑 C와 합의: Silver가 합성 경로를 읽을 수 있게 읽기 경로 지정(예: `read_bronze(bucket, prefix)`), 콤마 숫자 파싱(`"1,047.55"`)을 Silver에서 처리할지.
- [ ] T052 🧑 Train 구간(10/30~11/12) 종료 후 통계를 `train-v1`로 교체해 다시 생성하고 `generator_version`을 확정한다.
- [ ] T053 `spec.md`·`plan.md`의 미결 항목(상태 문구 확정, 참조 후보 조건 σ 배수·`p99` 상한 70/100 결과)을 실제 구현 결과로 갱신한다.
- [ ] T054 🧑 `git push`와 PR 생성 (PR 본문에 `Closes #29`, spec·plan·tasks와 코드를 함께). 수동 대조 결과(T045)를 본문에 포함.

---

## 의존 관계와 실행 순서

- Phase 1 → Phase 2 → Phase 3(MVP) → Phase 4 → Phase 5 → Phase 6 → Phase 7 → Phase 8.
- Phase 2의 테스트(T007~T010)가 먼저 실패하는 것을 확인한 뒤 구현(T011~T018)을 한다.
- Phase 3~5의 expected 작성(T019~T021, T029~T030, T037~T038)과 검수(T022, T031, T039)는 **해당 단계의 생성 작업보다 먼저** 끝낸다.
- Phase 4(S-05·S-06)와 Phase 5(S-07·S-08)는 서로 독립이지만 `synth/disturb.py`를 함께 쓰므로 한 사람이 순서대로 하는 것을 권한다.
- 병렬 가능: T002·T003, T007~T010, T013, 각 단계의 expected 파일들, 각 단계의 테스트 파일들.

## 구현 전략

1. **MVP = Phase 1~3**: S-01~S-05를 만들고 현재 Silver로 읽히는 것까지. 여기서 멈추고 검토한다.
2. 이후 단계(Phase 4, 5)를 하나씩 더한다. 각 단계가 끝나면 `validate`가 통과해야 다음으로 간다.
3. 사람이 하는 작업(🧑)은 막히면 먼저 알린다: T004·T005(입력 준비), T022·T031·T039(검수), T051(C 합의), T052(11/12 이후), T054(push).

## Notes

- 실측 경로(`tms_cleansys/`)에는 어떤 작업도 쓰지 않는다. T010·T015·T050이 이를 강제하고 확인한다.
- 비밀값(MinIO·AWS 자격)은 코드·설정·로그에 쓰지 않는다(T050).
- 커밋은 작업 단위로 나누고(`feat:`, `test:`, `docs:` + 한국어), `expected/`는 생성 코드보다 먼저 커밋한다.
