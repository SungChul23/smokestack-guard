# Implementation Plan: K-TMS 학습용 합성 데이터 풀 (생성 + Kafka → Spark → Bronze 적재)

**Branch**: `50-b-k-tms-학습용-합성-데이터-풀-생성-및-kafkasparkbronze-적재` | **Date**: 2026-11-16 | **Spec**: [spec.md](spec.md) | **Issue**: #50

**Input**: Feature specification from `specs/b-collection/103-synthetic-training-pool/spec.md`

## Summary

합성 재료 구간(잠정 2026-10-30 ~ 11-10)의 실측에서 **일별 실측 양성 수**와 **모양별 사건 수**를 뽑아, 일별로 실측 양성과 1:1인 합성 양성 에피소드를 계획한다. 모양별 배분은 "하한 우선 + 나머지 실측 모양 비중"(배수 상한 3배)이고, 곡선은 1단계(규칙 기반 + 범위 무작위화)로 만든다. 에피소드는 **슬롯(30분)마다 스냅샷 하나**에 합쳐 담아 실측 구조(하루 약 50개)에 맞춘다.

생성기가 스냅샷을 **Kafka 토픽으로 발행**하고, **Spark가 읽어 학습용 합성 전용 Bronze 폴더**에 원문 스냅샷 파일(`snapshot.json.gz`, meta, manifest, `_SUCCESS`)로 적재한다. 실측 수집기와 실측 경로(`tms_cleansys/`)는 건드리지 않는다. 102의 코드(`k_tms_synthetic/synth/`)를 재사용한다.

이 plan은 **로컬 환경(Docker Compose)** 기준이다. AWS 리소스는 만들지 않는다.

## Technical Context

**Language/Version**: Python 3.12 (생성기, 102와 같음). Spark 작업은 기존 `sg-spark:3.5` 이미지(Spark 3.5.4, Java 17, Python 3)에서 실행한다([spark_migration_checklist.md](../../../spark_migration_checklist.md)).

**Primary Dependencies**: 102의 `numpy`·`pandas`·`pyyaml`. **신규**: Kafka 클라이언트 1개(발행용, 아래 Complexity Tracking). Spark의 Kafka 커넥터 `spark-sql-kafka-0-10_2.12:3.5.4`는 실행 때 `--packages`로 받는다(저장소에 추가하지 않음). 저장 라이브러리는 기존 `boto3`.

**Storage**: Kafka(로컬 컨테이너, 보존 기간 길게) → MinIO `bronze` 버킷(로컬). 입력 `data/ref_stats.csv`, `data/daily_targets.csv`는 저장소에 커밋하지 않는다(`k_tms_synthetic/data/`는 커밋 금지).

**Testing**: `pytest`(생성·계획·모양·라벨은 순수 파이썬 단위 테스트). Kafka·Spark 종단 검증은 Docker가 필요한 통합 테스트로 분리하고, 평소 `pytest`에는 포함하지 않는다.

**Target Platform**: 개발자 로컬(Windows + Docker Desktop, Linux 컨테이너). Spark는 Windows native를 쓰지 않는다(체크리스트 §1).

**Project Type**: 단일 프로젝트(102의 `k_tms_synthetic/`에 모듈 추가) + 컨테이너 실행 파일

**Performance Goals**: 재료 구간 약 11일분 풀 생성이 수 분 안에 끝남. 적재 파일 수는 슬롯당 1개 × 약 530슬롯 × 4파일 ≈ 2,100개

**Constraints**: 같은 설정이면 바이트 단위로 같은 결과, 실측 경로(`tms_cleansys/`) 쓰기 금지, 비밀값 코드·설정·커밋 금지, AWS 리소스 생성 없음, 메시지 크기 Kafka 한도 안

**Scale/Scope**: 성분 2(NOX, SOX) × 모양 6. 합성 양성은 재료 구간(10/30~11/10) 합계로 NOX 약 4,550, SOX 약 1,150(실측 일별 양성 합계와 1:1). 에피소드 길이 24칸, 사건당 양성 1.85개 가정 시 약 3,100 에피소드, 슬롯 약 530개에 나누면 스냅샷당 활성 합성 굴뚝 약 140행(예상, 원문 약 80KB)

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| 원칙 | 판정 | 근거 |
|---|---|---|
| I. 수집 연속성 | ✅ | 수집 Lambda·스케줄·`tms_cleansys/`를 건드리지 않는다. 쓰기는 학습용 합성 폴더뿐이고, 쓰기 함수(102의 `check_prefix`와 같은 규칙)가 `tms_cleansys/` 아래 경로를 거부한다. 원본 객체를 삭제·덮어쓰지 않는다(같은 경로의 같은 내용 재기록만 허용). |
| II. 비밀값 비공개 | ✅ | MinIO 계정은 환경 변수로만 받고 compose·코드·설정·로그에 쓰지 않는다(`.env`는 커밋하지 않는다). |
| III. 코드로 만들고 적용은 사람이 | ✅ | AWS 리소스를 만들지 않는다. 로컬 compose 파일은 코드로 두고 실행은 사람이 한다. |
| IV. 데이터 계약 우선 | ⚠️ | 학습용 폴더 구조와 메시지 형식은 [contracts](contracts/)에 먼저 쓴다(Phase 1). Silver·ML-ready가 이 폴더를 읽는 변경은 C의 계약 영역이라 **이 spec에서 하지 않는다**. |
| V. 같은 조건의 정직한 비교 | ✅ | 합성 포함 여부 비교는 E의 몫이다. 풀 쪽은 통계 구간·버전을 `manifest.jsonl`에 남겨 같은 조건을 재현할 수 있게 한다. |
| VI. 설명 가능한 결과 | ✅ | 모든 에피소드에 모양·참조 굴뚝·seed·통계 구간·라벨 건수를 기록한다. |

설계 후 재점검: IV는 contracts 작성(Phase 1)과 C 협의 후 통과로 바꾼다. 위반 예외는 없다.

### 권한·비용 영향

- 부여하는 AWS 권한: **없음**. 로컬 MinIO 계정은 개발자 로컬 값이다.
- 예상 비용 영향: **AWS 비용 없음**(로컬 Docker만). 이후 클라우드(MSK, Glue)로 옮길 때는 A와 협의하고 별도 plan으로 비용을 적는다.

## 설계 결정 (Phase 0 결과)

| # | 결정 | 이유 |
|---|---|---|
| D1 | **슬롯마다 스냅샷 1개**에 활성 합성 에피소드의 굴뚝 행을 합쳐 담는다 | 실측은 하루 약 50개 스냅샷, 같은 측정이 거의 한 번만 나타난다(`raw_lines`≈`unique_stack_slots`). 102의 "10분마다 같은 내용 3번 반복"은 학습용에 쓰지 않는다. 파일 수가 실측 규모가 된다. |
| D2 | **일별 예산 = 그날 실측 양성 × `base_ratio`**, 모양별 배정은 재료 구간 전체로 계산해 날짜에 나눔 | 하한 N은 기간 단위, 예산은 일 단위라 분리해서 계산해야 한다(spec FR-006). |
| D3 | 모양 배분 `floor_then_real_mix`(기본), `sqrt_balance`(선택) | 1:1 총량 안에서 부족한 모양을 먼저 채운다. 모양별 합성/실측 상한 3배. |
| D4 | 곡선 1단계 = 규칙 기반 + 범위 무작위화. 배경·복귀는 `episode.py`(AR(1)), 모양 구간만 설정 범위에서 뽑아 `trajectory.inject`로 끼움 | 합성이 도움이 되는지 모르는 상태에서 템플릿·파라미터 체계를 먼저 만들지 않는다. 모양 구간 생성 함수만 교체 가능하게 분리한다. |
| D5 | **모양 판정 함수 `classify_shape`**를 파이썬으로 구현해, 생성한 궤적이 의도한 모양으로 판정되는지 확인 | Athena 쿼리와 같은 규칙(EXCEED → PLATEAU → OVER → SPIKE → GRADUAL → OTHER). SC-010. |
| D6 | **합성 굴뚝은 성분 하나**, 에피소드 하나 = 합성 굴뚝 하나. 측정하지 않는 성분 필드는 `None` | 실측 NOX+SOX 쌍 굴뚝은 만들지 않는다(NOX·SOX 독립 생성, 주간 보고 결정 6). |
| D7 | 에피소드 길이 = warmup(기본 12칸, 최소 6) + 모양 구간 + 복귀(기본 6칸) | E 피처가 이전 값을 최대 6칸 본다(401 FR-004). 음성 수는 이 길이에서 결정된다. 설정으로 조절. |
| D8 | Kafka: 토픽 `tms.synthetic.train`, 파티션 1, 메시지 키 `run_ts`, 값은 응답 원문 JSON(바이트), 헤더에 풀 이름·생성기 버전·통계 버전 | 처리량이 작고 순서 단순화가 더 중요하다. |
| D9 | Spark는 `startingOffsets=earliest` + `trigger(availableNow=True)`로 일괄 처리하고, `foreachBatch` 안에서 **파일 이름을 지정해** `boto3`로 쓴다 | Spark 기본 저장은 `part-…` 이름만 만들어 `snapshot.json.gz`를 지정할 수 없다. 배치가 작아(스냅샷 약 100KB) 드라이버에서 처리해도 된다. |
| D10 | `snapshot.meta.json`·`manifest.json`은 Spark 작업이 **`synth.snapshot.make_files`를 재사용**해 원문과 `run_ts`로 계산한다 | 파일 모드 산출물과 바이트가 같아야 한다(SC-005). 같은 함수를 쓰면 보장이 쉽다. `make_files`의 시각 필드가 `run_ts`에서 결정적으로 유도되는지 Phase 1에서 확인한다. |
| D11 | 저장 경로는 **템플릿**으로 받는다: 풀 모드 `<root>/ingest_date=/hour=/run_ts=/`, 시험 모드 `<root>/episode=<id>/ingest_date=…` | 102의 평가용 16개 에피소드는 모두 같은 시각에 시작해 `run_ts`가 겹친다. 시험 모드에서 에피소드로 구분해야 한다. |
| D12 | 멱등: 경로를 메시지의 키(`run_ts`, 시험 모드는 + 에피소드)로만 정함. `_SUCCESS`는 데이터 파일 저장·해시 검증 뒤에만 | 중복 전달·재시작에도 같은 경로에 같은 내용이 쓰인다. |
| D13 | 파이프라인은 **평가용 16개 에피소드로 먼저 검증**하고, 그 뒤 학습용 풀로 확장 | 파이프라인은 데이터 모양과 무관하다. 학습용 생성기가 없어도 검증 가능하다. |

## 풀 계획 알고리즘 (D2, D3)

입력: `data/daily_targets.csv`(날짜 × 성분별 실측 양성 수), 모양별 직전 단서 사건 수, 설정.

```
1. 성분별로 예산 S_total = Σ_일 (그날 실측 양성 × base_ratio)          # 양성 행 단위
2. 모양 k의 하한 사건 수 F_k = max(0, N_성분 − real_events_k)           # N은 직전 단서 사건 수 기준
   모양 k의 상한 C_k = per_shape_cap × real_events_k
   F_k = min(F_k, C_k)                                                   # 상한 때문에 못 채우면 보고
3. 하한 양성 = Σ F_k × 사건당 양성(기본 1.85). 예산의 20%를 넘으면 경고
4. 나머지 예산을 실측 모양 비중대로 배분(모양별 상한 C_k 초과분은 다른 모양에 재분배)
5. 모양별 에피소드 수 → 날짜별로 배치(일별 예산 비율대로, 무작위 시작 슬롯, seed 고정)
6. 각 에피소드에 참조 굴뚝·seed·합성 굴뚝 코드(SYN-T-…) 부여
```

- 사건당 양성 수는 계획용 기본값이고, 생성 후 `label.py`로 센 실제 값으로 보정한 뒤 모자라거나 넘치면 에피소드를 추가·제거한다(한 번 반복).
- 결과는 `pool_plan.jsonl`(에피소드 목록)과 요약 표(성분 × 모양 × 하한/상한/배정)로 남긴다.

## 모양 곡선 범위 (D4, 제안값)

아래 범위는 **시작값(제안)**이고, 판정 규칙(spec FR-002)을 통과하는지 `classify_shape`로 확인하며 조정한다. 값은 기준대비율이다.

| 모양 | 범위(예시) | 통과해야 하는 규칙 |
|---|---|---|
| GRADUAL | 120분 전 0.50~0.69, 이후 4~6칸 연속 증가(칸당 +0.03~0.09), 30분 전 ≥ 0.80, 진입 0.90~0.99 | 직전 4값 엄격 증가, 30분 전 ≥ 0.80, 120분 전 < 0.70 |
| SPIKE | 직전 0.40~0.69, 90% 이상 1~2칸(0.90~1.05), 복귀 | 90% 이상 ≤ 2칸, 30분 전 < 0.70 |
| EXCEED | 직전 0.50~0.89, 100% 이상 3~6칸(1.00~1.30) | 100% 이상 ≥ 3칸 |
| PLATEAU | 진입 0.90~0.95, 90% 이상 4~8칸 유지(최고 < 1.00) | 90% 이상 ≥ 4칸, 최고 < 1.00, 진입 ≤ 2회 |
| OVER | 0.85~0.92 사이 진동, 90% 경계 3~5회 진입 | 진입 ≥ 3회 |
| OTHER | 직전 0.70~0.89, 90% 이상 1~3칸 | 위 어느 모양에도 안 걸림 |

## Project Structure

### Documentation (this feature)

```text
specs/b-collection/103-synthetic-training-pool/
├── plan.md              # 이 파일
├── spec.md
├── contracts/           # Phase 1: 학습용 폴더 구조, 메시지 형식, manifest.jsonl 필드
├── data-model.md        # Phase 1: 일별 목표표, 풀 계획, 설정 필드
├── quickstart.md        # Phase 1: 실행 순서
└── tasks.md             # /speckit-tasks 출력(이 명령이 만들지 않음)
```

### Source Code (repository root)

```text
k_tms_synthetic/
├── synth/
│   ├── pool.py              # 신규: 일별 예산, 하한·상한, 모양 배분, 에피소드 목록(pool_plan)
│   ├── shapes.py            # 신규: 모양별 범위에서 궤적 샘플링, classify_shape
│   ├── label.py             # 신규: label-v1 양성·음성·제외 건수(T055~T058 재사용)
│   ├── pack.py              # 신규: 슬롯별 스냅샷으로 에피소드 행을 합침
│   ├── publish.py           # 신규: 스냅샷을 Kafka로 발행
│   ├── generate.py          # 수정: 풀 모드 추가(기존 평가용 흐름은 그대로)
│   ├── validate.py          # 수정: 세트 점검, --root 인자
│   └── (plan, stats, episode, scenarios/trajectory, snapshot, schedule, writer, compare: 102 재사용)
├── ingest/
│   └── spark_ingest.py      # 신규: Kafka → Bronze 파일 쓰기(Spark 작업, 컨테이너에서 실행)
├── kafka/
│   └── docker-compose.yml   # 신규: Kafka(KRaft 단일 브로커). MinIO·Spark는 기존 환경 사용
├── config/
│   └── pool.yaml            # 신규: base_ratio, allocation, min_events, per_shape_cap, 모양 범위, 기간, 에피소드 길이
├── data/                    # 커밋 금지: ref_stats.csv, daily_targets.csv
└── tests/
    ├── test_pool.py
    ├── test_shapes.py
    ├── test_label.py
    ├── test_pack.py
    ├── test_publish.py          # 메시지 만들기까지(브로커 없이)
    └── integration/             # Docker 필요: Kafka → Spark → 파일 비교
```

**Structure Decision**: 102의 `k_tms_synthetic/`에 모듈을 추가한다. `ingest/spark_ingest.py`는 `synth` 패키지를 컨테이너의 `PYTHONPATH`로 읽어 재사용한다. 저장소 루트의 `src/`(C의 Silver)와 `infra/`(Terraform)는 건드리지 않는다.

## 구현 순서 (tasks의 뼈대)

| 단계 | 내용 | 완료 기준 |
|---|---|---|
| 0. 선행 확인 | (가) `n_snap` 쿼리로 실측 스냅샷 구조 확정 (나) 재료 구간(10/30~11/10)으로 `ref_stats.csv`, `daily_targets.csv` 재추출 (다) 실측 `run_ts`와 `mesure_dt` 차이 확인(합성 `run_ts` 규칙) (라) `make_files`의 시각 필드가 `run_ts`에서 결정적인지 확인 | 결과가 plan의 가정과 맞음. 다르면 plan 수정 |
| 1. 계획 | `pool.py`: 예산, 하한, 상한, 배분 + 단위 테스트 | 합성 계획 수가 규칙과 일치, 상한 미달 보고 |
| 2. 모양 | `shapes.py`: 샘플링 + `classify_shape` | 모든 샘플이 의도한 모양으로 판정(SC-010) |
| 3. 라벨 | `label.py` + 102 `expected`의 `label_expect` 대조 | 102 에피소드의 라벨 건수가 expected와 일치 |
| 4. 합치기 | `pack.py`: 슬롯 스냅샷, `manifest.jsonl` | 에피소드 추적 가능, 스냅샷 크기 한도 안 |
| 5. 생성·점검 | 풀 생성 + `validate`(세트 점검) | SC-001~004, 007~010 통과 |
| 6. Kafka·Spark 환경 | compose, 발행, Spark 적재 + **102 평가용 16개로 검증**(시험 모드) | 파일 모드와 바이트 동일 |
| 7. 풀 적재 | 풀을 Kafka → Spark → 학습용 폴더로(풀 모드) | SC-005, 006(멱등·재시작) |
| 8. 문서·마무리 | README, quickstart, 계약 문서 확정, PR | 검수자 확인, C 협의 반영 |

## 미결·위험

| 항목 | 내용 | 대응 |
|---|---|---|
| 실측 스냅샷 구조 | `n_snap` 결과 대기. 하루 약 50개·행 중복 없음이 사실이어야 D1이 맞다 | 단계 0(가). 다르면 D1 수정 |
| 합성 `run_ts` 규칙 | 실측은 `run_ts`가 수집 시각이라 `mesure_dt`보다 늦다. 늦는 정도를 모른다 | 단계 0(다). 확인 전까지 슬롯 시각 + 10분 단위 첫 시각을 임시값으로 |
| 사건당 양성 수 1.85 | 실측 평균이고 합성 곡선에서는 다를 수 있다 | 생성 후 `label.py`로 보정(1회 반복) |
| 모양 범위의 임의성 | 1단계 범위는 사람이 정한 값 | `classify_shape` 통과로 최소한의 일관성 확인. 효과는 E의 비교 실험에서 판단 |
| SOX GRADUAL·OVER(14~16건) | 배수 상한 때문에 하한 N을 못 채움 | 계획 요약 표에 미달 보고. 실측이 쌓이길 기다림 |
| Kafka 메시지 크기 | 스냅샷당 약 140행(예상)이면 약 80KB, 한도(기본 약 1MB) 안. 가정이 틀리면 초과 | 단계 4에서 실제 크기 확인, 필요 시 압축·분할 |
| 외부 검증 기간 | E와 11/11 이후 확정 필요 | 잠정값으로 진행, 기간은 설정 |
| Silver 읽기 경로 | 학습용 폴더를 Silver·ML-ready가 읽으려면 C의 변경 필요 | 이 spec 범위 밖. C에게 요청 |
| Kafka·Spark 도구 버전 | Kafka 이미지·클라이언트 버전 미확정 | 단계 6 시작 때 확정, 이 plan에 반영 |

## Complexity Tracking

| 항목 | 이유 | 더 단순한 대안을 안 쓰는 이유 |
|---|---|---|
| 외부 패키지 추가(Kafka 클라이언트) | Kafka로 발행하려면 필요 | 표준 라이브러리에는 Kafka 클라이언트가 없다. 수집 Lambda가 아니므로 "외부 패키지 금지" 규칙(Lambda 한정)에 해당하지 않지만 이유를 적는다. |
| 슬롯 스냅샷 합치기(`pack.py`) | 파일 수를 실측 규모로 맞추고 Kafka 메시지 수를 줄임 | 에피소드마다 스냅샷을 만들면 102처럼 파일이 수만 개가 된다(에피소드 약 3,100개 × 슬롯). |
| 모양 판정 함수(`classify_shape`) | 생성 곡선이 의도한 모양인지 자동 확인 | 눈으로 확인하면 약 3,100개를 검증할 수 없다. |
