# Implementation Plan: K-TMS 학습용 합성 데이터 (일 단위 생성 + Kafka → Spark → Bronze 적재)

**Branch**: `50-b-k-tms-학습용-합성-데이터-풀-생성-및-kafkasparkbronze-적재` | **Date**: 2026-11-16 | **Spec**: [spec.md](spec.md) | **Issue**: #50

**Input**: Feature specification from `specs/b-collection/103-synthetic-training-pool/spec.md`

## Summary

합성 K-TMS 데이터를 **날짜 단위로 생성**(10/30~어제는 backfill로 하루치씩 배치 발행, **지금부터는 실측처럼 30분 슬롯마다 하나씩 자기 `run_ts` 시각에 방출**)해 **Kafka로 발행하고 Spark가 학습용 합성 전용 Bronze 폴더에 원문 스냅샷 파일**(`snapshot.json.gz`, meta, manifest, `_SUCCESS`)로 적재한다. 적재된 데이터는 실측(cleansys)과 같은 경로 구조(`ingest_date=/hour=/run_ts=/`)로 쌓여 Silver → ML-ready를 거쳐 모델 학습에 쓰인다. **학습에 얼마나 쓸지는 ML 담당자(E)가 `manifest.jsonl` 태그로 고른다.**

생성량은 설정의 **(성분 × 모양)별 하루 에피소드 수**로 정하며, 시작값은 그날 실측 양성과 **1:1**이다(권고값). 에피소드는 (시작 날짜, 성분, 모양, 번호)에서 정해지는 seed로 통째로 만들어져서, 자정을 걸치는 에피소드도 **저장된 상태 없이** 날짜별로 독립 생성된다. 슬롯마다 스냅샷 1개(하루 48개)에 활성 에피소드의 행을 합쳐 담는다. 실측 수집기와 실측 경로(`tms_cleansys/`)는 건드리지 않는다. 102의 코드는 **새 폴더 `k_tms_synthetic_train/`로 필요한 모듈만 복사**해서 쓴다(패키지 `synth_train`, D15).

이 plan은 **로컬 환경(Docker Compose)** 기준이다. AWS 리소스는 만들지 않는다.

## Technical Context

**Language/Version**: Python 3.12 (102와 같음). Spark 작업은 기존 `sg-spark:3.5` 이미지(Spark 3.5.4, Java 17, Python 3)에서 실행한다([spark_migration_checklist.md](../../../spark_migration_checklist.md)).

**Primary Dependencies**: `numpy`·`pandas`·`pyyaml`(102와 같음). **신규**: Kafka 클라이언트 1개(발행용, Complexity Tracking). Spark의 Kafka 커넥터 `spark-sql-kafka-0-10_2.12:3.5.4`는 실행 때 `--packages`로 받는다(저장소에 추가하지 않음). 저장 라이브러리는 기존 `boto3`.

**Storage**: Kafka(로컬 컨테이너, 보존 기간 길게) → MinIO `bronze` 버킷(로컬). 입력 `data/ref_stats.csv`는 저장소에 커밋하지 않는다(`k_tms_synthetic_train/data/`는 커밋 금지).

**Testing**: `pytest`(생성·모양·라벨은 순수 파이썬 단위 테스트). Kafka·Spark 종단 검증은 Docker가 필요한 통합 검증으로 분리한다.

**Target Platform**: 개발자 로컬(Windows + Docker Desktop, Linux 컨테이너). Spark는 Windows native를 쓰지 않는다.

**Project Type**: 단일 프로젝트(새 폴더 `k_tms_synthetic_train/`, 102 모듈은 복사) + 컨테이너 실행 파일

**Performance Goals**: 하루치(스냅샷 48개, 약 6,600행) 생성이 수 초~수십 초. backfill 17일(10/30~11/16)이 수 분 안에 끝남

**Constraints**: 같은 날짜·같은 설정이면 바이트 단위로 같은 결과, 실측 경로(`tms_cleansys/`) 쓰기 금지, 비밀값 코드·설정·커밋 금지, AWS 리소스 생성 없음, 메시지 크기 Kafka 한도 안

**Scale/Scope**: 성분 2(NOX, SOX) × 모양 6. 하루 에피소드 약 275개(NOX 218, SOX 57, 아래 표), 하루 약 6,600행, 스냅샷당 약 140행(원문 약 80KB). backfill 17일 ≈ 스냅샷 816개 ≈ 파일 3,300개

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| 원칙 | 판정 | 근거 |
|---|---|---|
| I. 수집 연속성 | ✅ | 수집 Lambda·스케줄·`tms_cleansys/`를 건드리지 않는다. 쓰기는 학습용 합성 폴더뿐이고, 쓰기 함수(`check_prefix`)가 `tms_cleansys/` 아래 경로를 거부한다(테스트로 확인). 원본 객체를 삭제·덮어쓰지 않는다(같은 경로의 같은 내용 재기록만 허용). |
| II. 비밀값 비공개 | ✅ | MinIO 계정은 환경 변수로만 받고 compose·코드·설정·로그에 쓰지 않는다(`.env`는 커밋하지 않는다). |
| III. 코드로 만들고 적용은 사람이 | ✅ | AWS 리소스를 만들지 않는다. 로컬 compose 파일은 코드로 두고 실행은 사람이 한다. |
| IV. 데이터 계약 우선 | ⚠️ | 학습용 폴더 구조와 메시지 형식은 contracts에 먼저 쓴다(Phase 8). Silver·ML-ready가 이 폴더를 읽는 변경은 C의 계약 영역이라 **협의가 필요**하다(합성이 ML로 흐르는 핵심 경로). |
| V. 같은 조건의 정직한 비교 | ✅ | 합성 포함 여부 비교는 E의 몫이다. 생성기는 통계 버전·생성기 버전을 `manifest.jsonl`에 남겨 같은 조건을 재현할 수 있게 한다. |
| VI. 설명 가능한 결과 | ✅ | 모든 에피소드에 날짜·모양·참조 굴뚝·seed·통계 버전·라벨 건수를 기록한다. |

### 권한·비용 영향

- 부여하는 AWS 권한: **없음**. 로컬 MinIO 계정은 개발자 로컬 값이다.
- 예상 비용 영향: **AWS 비용 없음**(로컬 Docker만). 클라우드(MSK, Glue)로 옮길 때는 A와 협의하고 별도 plan으로 비용을 적는다.

## 설계 결정 (Phase 0 결과)

| # | 결정 | 이유 |
|---|---|---|
| D1 | **슬롯마다 스냅샷 1개**(하루 48개)에 활성 합성 에피소드의 행을 합쳐 담는다 | 실측은 같은 (굴뚝, 측정 시각)이 스냅샷 한 개에만 나타난다(2026-11-05, 154,842건 모두 `n_snap = 1`). 102의 "10분마다 3번 반복"은 학습용에 쓰지 않는다. |
| D2 | **하루 생성량 = 설정의 (성분 × 모양)별 하루 에피소드 수**. 시작값은 아래 표(그날 실측 양성과 1:1) | 선택은 ML 담당자 몫이므로 생성기는 규칙으로 계산하지 않고 숫자만 받는다. 1:1, 하한, 배수는 권고 근거로만 남긴다. |
| D3 | 에피소드는 **(시작 날짜, 성분, 모양, 번호)에서 정해지는 seed로 통째로** 만든다. 시작 슬롯은 하루 48칸에 균등 배치 | 같은 에피소드는 언제 만들어도 같다. 상태를 저장하지 않아도 날짜별로 독립 생성된다. |
| D4 | **자정을 걸치는 에피소드를 허용**하고, 하루를 만들 때 전날 시작분도 seed로 다시 만들어 그날 슬롯에 넣는다 | 에피소드를 하루 안에 가두면 합성 양성이 낮에 몰려 E의 시간대 피처(`hour_sin`, `hour_cos`)로 모델이 "합성 = 낮"을 배운다. |
| D5 | 곡선 1단계 = 규칙 기반 + 범위 무작위화. 배경·복귀는 `episode.py`(AR(1)), 모양 구간만 설정 범위에서 뽑아 `trajectory.inject`로 끼움 | 합성이 도움이 되는지 모르는 상태에서 템플릿·파라미터 체계를 먼저 만들지 않는다. 모양 구간 생성 함수만 교체 가능하게 분리한다. |
| D6 | **모양 판정 함수 `classify_shape`**를 파이썬으로 구현해, 생성한 궤적이 의도한 모양으로 판정되는지 확인 | Athena 쿼리와 같은 규칙(EXCEED → PLATEAU → OVER → SPIKE → GRADUAL → OTHER). 샘플러가 의도와 다른 모양을 뽑으면 다시 뽑는다. |
| D7 | **합성 굴뚝은 성분 하나**, 에피소드 하나 = 합성 굴뚝 하나. 굴뚝 코드는 `SYN-T-<시작날짜>-<성분>-<모양>-<번호>`. 측정하지 않는 성분 필드는 `None` | 코드만으로 날짜·모양을 알 수 있고 실측 코드와 겹치지 않는다. NOX·SOX 독립 생성(주간 보고 결정 6). |
| D8 | 에피소드 길이 = warmup(기본 12칸, 최소 6) + 모양 구간 + 복귀(기본 6칸). 하루(48칸) 미만 | E 피처가 이전 값을 최대 6칸 본다(401 FR-004). 음성 수는 이 길이에서 결정된다. 설정으로 조절. |
| D9 | Kafka: 토픽 `tms.synthetic.train`, 파티션 1, 메시지 키 `run_ts`, 값은 응답 원문 JSON(바이트), 헤더에 생성기 버전·통계 버전 | 처리량이 작고 순서 단순화가 더 중요하다. |
| D10 | Spark는 `startingOffsets=earliest` + `trigger(availableNow=True)`로 일괄 처리하고, `foreachBatch` 안에서 **파일 이름을 지정해** `boto3`로 쓴다 | Spark 기본 저장은 `part-…` 이름만 만들어 `snapshot.json.gz`를 지정할 수 없다. 배치가 작아 드라이버에서 처리해도 된다. |
| D11 | `snapshot.meta.json`·`manifest.json`은 Spark 작업이 **복사한 `synth_train.snapshot.make_files`를 재사용**해 원문과 `run_ts`로 계산한다 | 파일 모드 산출물과 바이트가 같아야 한다(SC-005). `make_files`는 gzip `mtime=0`이고 모든 시각 필드가 `run_ts`에서 유도되어 결정적이다(확인됨). |
| D12 | 저장 경로는 **템플릿**: 풀 모드 `tms_synthetic_train/ingest_date=/hour=/run_ts=/`, 시험 모드 `tms_synthetic/episode=<id>/ingest_date=…` | 구현됨(`build_prefix`의 `root`·`episode_id`, `check_prefix`가 두 루트만 허용). 102 평가용 16개 에피소드는 같은 시각에 시작해 `run_ts`가 겹치므로 시험 모드에서 에피소드로 구분한다. |
| D13 | 멱등: 경로를 메시지의 키(`run_ts`, 시험 모드는 + 에피소드)로만 정함. `_SUCCESS`는 데이터 파일 저장·해시 검증 뒤에만 | 중복 전달·재시작에도 같은 경로에 같은 내용이 쓰인다. |
| D14 | 합성 `run_ts` = **측정 시각(KST → UTC) + 70분** (슬롯마다 1개, 하루 48개). 지연은 넣지 않는다 | 실측의 94.9%가 70~79분 뒤에 처음 나타난다(2026-11-05). 지연(+30·+60·+90분)은 실측 약 5%이며 학습용에는 결함이므로 제외한다(spec FR-005). `ingest_date`·`hour`는 이 UTC `run_ts`에서 정한다. |
| D15 | 코드는 **새 폴더 `k_tms_synthetic_train/`로 102 모듈을 복사**해 쓴다. 패키지 이름은 `synth_train`, 복사 출처 커밋은 README에 기록 | 102 PR(#29)과 독립시키고 평가용·학습용 폴더를 분리한다. 복사 대상은 끝나고 테스트된 안정적인 모듈이다. 패키지 이름이 `synth`와 같으면 한 환경에서 import가 충돌한다. |
| D16 | 발행은 두 방식이다. **배치**: 과거(10/30~어제, backfill)는 하루치(48개)를 한꺼번에. **방출(release)**: 지금부터는 각 스냅샷을 자기 `run_ts` 시각에 하나씩 | 방출은 실측(30분 슬롯이 갱신될 때 하나씩 도착)과 같은 도착 방식이다. 과거는 기다릴 수 없어 배치다. 두 방식의 Bronze 결과(경로·내용)는 같고 객체 수정 시각만 다르다. |
| D19 | `release`는 **멱등 명령**이다. 실행할 때마다 `run_ts ≤ 지금`이고 아직 안 올린 스냅샷만 발행한다. 올린 기록을 상태로 두지 않고 경로·내용의 결정성에 의존한다(이미 올린 것을 다시 올려도 같은 경로에 같은 내용). 오늘·내일 하루치가 없으면 먼저 생성한다 | 10분마다 실행해도, 실행을 건너뛰었다 재개해도(밀린 것을 한꺼번에) 결과가 같다. 스케줄러는 단순히 이 명령을 주기로 부르기만 하면 된다. |
| D17 | 참조 통계는 **고정 버전**(`ref-1030-1110`)을 쓰고 manifest에 기록한다. 합성의 날짜와 통계 기간은 독립 | 날짜가 늘어도 통계를 다시 뽑지 않는다. 통계를 새로 뽑으면 버전을 올린다. |
| D18 | **파이프라인(Kafka → Spark → Bronze)은 평가용 16개 에피소드로 먼저 검증**하고, 그 뒤 학습용 데이터로 확장 | 파이프라인은 데이터 모양과 무관하다. 학습용 생성기가 없어도 검증 가능하다. |

## 하루 생성량 시작값 (D2)

**계산 근거(한 번만 계산, 권고값)**

1. 재료 기간(10/31~11/10, 완전한 11일) 실측 일평균 양성: **NOX 약 403, SOX 약 103**. 합성 양성을 같게(1:1).
2. 사건당 양성 약 1.85 → 하루 에피소드 NOX 약 218, SOX 약 56.
3. 모양 배분은 "부족한 모양을 먼저, 나머지는 실측 사건 비중대로"(하한 N: NOX 150, SOX 50, 14일 직전 단서 사건 수 기준을 하루로 환산).

| 모양 | NOX 에피소드/일 | SOX 에피소드/일 |
|---|---|---|
| OTHER | 125 | 24 |
| SPIKE | 49 | 14 |
| EXCEED | 11 | 7 |
| PLATEAU | 11 | 4 |
| OVER | 11 | 4 |
| GRADUAL | 11 | 4 |
| **합계** | **218** | **57** |

- 하루 행 수: 에피소드 275개 × 24칸 ≈ 6,600행 → 스냅샷당 약 140행(원문 약 80KB).
- 희귀한 모양은 실측 사건보다 많이 만든다(예: NOX GRADUAL 하루 11개 vs 실측 약 4개). SOX GRADUAL·OVER는 11일에 약 44개로 실측(약 11개)의 4배라 **같은 모양의 변형이 반복**된다. 많이 만들어 두고 선택은 E가 한다.
- 위 숫자는 시작값이다. `config/daily.yaml`의 숫자만 바꾸면 되고 코드는 바뀌지 않는다.

## 하루 생성 알고리즘 (D3, D4)

```
generate_day(date):                                       # 날짜(KST) 하나
  episodes = []
  for d in [date - 1일, date]:                              # 전날 시작분(자정을 걸침) + 그날 시작분
    for (성분, 모양, 번호) in 설정의 하루 에피소드 수:
      seed = f(run.seed, d, 성분, 모양, 번호)                # 결정적
      start_slot = rng(seed).integers(0, 48)                # 시작 칸(하루 48칸에 균등)
      series = 에피소드 곡선(참조 굴뚝, 모양 궤적, warmup, 복귀, seed)   # 통째로 생성
      episodes.append((d, start_slot, series))
  for 슬롯 0..47 of date:                                   # 그날 48칸
    items = 그 슬롯에 걸친 모든 에피소드의 행
    snapshot = make_snapshot(items); run_ts = 슬롯 시각(UTC) + 70분
  manifest: d == date 인 에피소드만 기록                      # 시작 날짜 기준, 중복 기록 방지
```

- 같은 에피소드는 어느 날짜를 만들 때 다시 만들어도 **같은 곡선**이다(seed가 같으므로). 그래서 전날 결과를 읽지 않는다.
- 어떤 날짜든 순서와 무관하게 만들 수 있고(backfill), 같은 날짜를 다시 만들면 바이트가 같다.
- backfill 첫날(10/30)에는 10/29 시작 에피소드도 seed로 만들어 앞쪽 슬롯이 비지 않게 한다.

## 방출 알고리즘 (D16, D19)

```
release(now=현재 시각 UTC):                                  # 10분마다 실행해도 안전(멱등)
  for date in [오늘(KST), 내일(KST)]:
    없으면 generate_day(date)                                   # 미리 생성(결정적, 저렴)
  for 스냅샷 in 오늘·내일의 스냅샷 중 run_ts <= now:             # 아직 올릴 때가 안 된 것은 제외
    publish(스냅샷)                                             # 경로·내용이 같아 다시 올려도 결과가 같음
```

- 슬롯 09:00(KST)의 스냅샷은 `run_ts` = 10:10(KST)이므로 10:10 이후 첫 실행에서 올라간다. 10분 주기면 지연은 10분 이내다.
- 실행이 멈췄다 재개되면 `run_ts ≤ 지금`인 밀린 스냅샷이 한꺼번에 올라간다.
- "이미 올렸는가"를 기억하지 않아도 되도록 최근 몇 시간 분량을 다시 올려도 문제가 없다(멱등). 올리는 양은 `run_ts`가 지금 이전이고 일정 시간(예: 3시간) 안인 것으로 제한할 수 있다.
- 스케줄러(cron, Windows 작업 스케줄러, Airflow)는 `python -m synth_train release --config config/daily.yaml`을 10분마다 부르기만 하면 된다.

## 모양 곡선 범위 (D5, 제안값)

아래 범위는 **시작값(제안)**이고, 판정 규칙(spec FR-002)을 통과하는지 `classify_shape`로 확인하며 조정한다. 값은 기준대비율(%)이다.

| 모양 | 범위(예시) | 통과해야 하는 규칙 |
|---|---|---|
| GRADUAL | 시작 50~69, 4~7칸 연속 증가(칸당 +3~9), 진입 90~99 | 직전 4값 엄격 증가, 30분 전 ≥ 80, 120분 전 < 70 |
| SPIKE | 직전 40~69, 90% 이상 1~2칸(90~105), 복귀 | 90% 이상 ≤ 2칸, 30분 전 < 70 |
| EXCEED | 직전 50~89, 100% 이상 3~6칸(100~130) | 100% 이상 ≥ 3칸 |
| PLATEAU | 진입 90~99, 90% 이상 4~8칸 유지(최고 < 100) | 90% 이상 ≥ 4칸, 최고 < 100, 진입 ≤ 2회 |
| OVER | 82~89와 90~95 사이 진동, 90% 경계 3~5회 진입 | 진입 ≥ 3회 |
| OTHER | 직전 70~89, 90% 이상 1~3칸(90~99) | 위 어느 모양에도 안 걸림 |

## Project Structure

### Documentation (this feature)

```text
specs/b-collection/103-synthetic-training-pool/
├── plan.md              # 이 파일
├── spec.md
├── contracts/           # Phase 8: 학습용 폴더 구조, 메시지 형식, manifest.jsonl 필드
├── data-model.md        # Phase 8: 설정 필드, 하루 생성량, manifest
├── quickstart.md        # Phase 8: 실행 순서
└── tasks.md
```

### Source Code (repository root)

```text
k_tms_synthetic_train/               # 신규 폴더 (102의 k_tms_synthetic/은 바꾸지 않음)
├── README.md                        # 복사 출처(102 커밋 6a6acaf)와 실행 방법
├── requirements.txt
├── synth_train/
│   ├── snapshot.py                  # 복사 + 학습용 루트(TRAIN_ROOT)·에피소드 폴더 없는 경로 (완료)
│   ├── schedule.py                  # 복사 (슬롯 시각표. 슬롯당 1개·run_ts +70분 규칙은 pack/daily에서 적용)
│   ├── writer.py                    # 복사 + 두 루트 허용, tms_cleansys/ 거부 유지 (완료)
│   ├── episode.py                   # 복사 (AR(1) 배경)
│   ├── stats.py                     # 복사 (참조 굴뚝 선택)
│   ├── plan.py                      # 복사 (설정 읽기 등 필요한 함수만)
│   ├── scenarios/trajectory.py      # 복사 (inject)
│   ├── label.py                     # (후속: Silver·ML-ready 연결 후) label-v1 양성·음성·제외 건수
│   ├── shapes.py                    # 신규: 모양별 궤적 샘플링, classify_shape
│   ├── daily.py                     # 신규: 하루 에피소드 목록, seed, 시작 슬롯, 전날 시작분 재생성
│   ├── pack.py                      # 신규: 슬롯별 스냅샷으로 에피소드 행을 합침
│   ├── generate.py                  # 신규: generate-day, backfill
│   ├── publish.py                   # 신규: 스냅샷을 Kafka로 발행(배치)
│   ├── release.py                   # 신규: run_ts가 지난 스냅샷만 발행하는 멱등 명령(방출)
│   ├── validate.py                  # Phase 5에서 102 것을 복사(평가용 compare 의존은 제외)하고 세트 점검 추가
│   └── __main__.py                  # generate-day, backfill, publish, release, validate, summary 명령
├── ingest/
│   └── spark_ingest.py              # 신규: Kafka → Bronze 파일 쓰기(Spark 작업, 컨테이너에서 실행)
├── kafka/
│   └── docker-compose.yml           # 신규: Kafka(KRaft 단일 브로커). MinIO·Spark는 기존 환경 사용
├── config/
│   └── daily.yaml                   # 신규: 하루 에피소드 수, 모양 범위, 에피소드 길이, 참조 선택, 경로
├── data/                            # 커밋 금지: ref_stats.csv
└── tests/
    ├── fixtures/                    # ref_stats_sample.csv, 102 expected(라벨·모양 판정 시험용, 출처 기록)
    ├── (복사한 모듈의 테스트 9개)
    ├── test_label.py, test_classify_shape.py, test_shapes.py
    ├── test_daily.py, test_pack.py, test_generate.py
    ├── test_publish.py              # 메시지 만들기까지(브로커 없이)
    └── integration/                 # Docker 필요: Kafka → Spark → 파일 비교
```

**Structure Decision**: 새 폴더 `k_tms_synthetic_train/`에 102 모듈 중 필요한 것만 복사하고(평가용 전용 `compare.py`, 8개 시나리오 설정, `expected/`는 복사하지 않음) 학습용 모듈을 추가한다. 복사한 모듈은 `synth_train` 패키지로 import를 바꾼다. `ingest/spark_ingest.py`는 컨테이너의 `PYTHONPATH`에서 `synth_train`을 읽는다. 평가용 16개 에피소드(파이프라인 시험 재료)는 같은 브랜치의 `k_tms_synthetic/`에서 만든 `out/`을 입력으로 쓴다. 저장소 루트의 `src/`(C의 Silver)와 `infra/`(Terraform)는 건드리지 않는다.

## 구현 순서 (tasks의 뼈대)

| 단계 | 내용 | 완료 기준 |
|---|---|---|
| 0. 선행(완료) | 스냅샷 구조·`run_ts` 규칙 확인, 참조 통계, 모듈 복사, 경로 루트 | 가정 확정 |
| 1. 설정 | `config/daily.yaml`(하루 에피소드 수, 모양 범위, 길이) | 값이 plan 표와 같음 |
| 2. 라벨·모양 판정 | `label.py`, `classify_shape` | 102 expected와 건수 일치, 고정 궤적이 올바른 모양 |
| 3. 모양 곡선 | `shapes.py` 샘플링 + 에피소드 조립 | 모든 샘플이 의도한 모양으로 판정 |
| 4. 하루 생성 | `daily.py`, `pack.py`, `generate.py`(generate-day, backfill), manifest | 같은 날짜 바이트 동일, 날짜 순서 무관, 시간대 분포 |
| 5. 점검 | `validate`(세트 점검), 요약 명령 | 규칙 위반이 모두 잡힘 |
| 6. Kafka·Spark | compose, 발행, Spark 적재 + 평가용 16개로 검증, `release`(방출) | 파일 모드와 바이트 동일, 멱등, 재시작, 방출이 `run_ts` 이후에만 올림 |
| 7. 학습용 적재 | backfill 결과를 Kafka → Spark → 학습용 폴더로(배치), 이후 방출을 10분 주기로 | 10/30~어제 모두 적재, validate 통과, 오늘 슬롯이 시각대로 쌓임 |
| 8. 문서·협의 | contracts, quickstart, README, C·E 협의, 검수, PR | 협의 반영, PR |

## 미결·위험

| 항목 | 내용 | 대응 |
|---|---|---|
| Silver 읽기 경로 | Silver가 `tms_cleansys/`만 읽어 합성이 ML로 흐르지 않음 | **C와 협의(핵심 경로)**. 이 spec은 코드를 변경하지 않음 |
| 검증 데이터 혼입 | 합성이 실측과 같은 날짜로 들어와 시간 기준 분할에서 검증·평가에 섞일 수 있음 | E가 `SYN-` 굴뚝 코드로 제외해야 함(합의) |
| 참조 통계와 외부 검증 겹침 | 통계 기간(10/30~11/10)과 E의 외부 검증(10/31~11/10)이 같아 누출 가능 | E가 외부 검증을 11/11 이후로 바꿀 수 있는지 확인 |
| 모양 범위의 임의성 | 1단계 범위는 사람이 정한 값 | `classify_shape` 통과로 최소한의 일관성 확인. 효과는 E의 비교 실험에서 판단 |
| SOX GRADUAL·OVER | 실측 사건이 14~16건뿐이라 많이 만들수록 같은 모양이 반복됨 | 많이 만들어 두되 선택은 E. 실측이 쌓이길 기다림 |
| 사건당 양성 1.85 | 실측 평균이며 합성 곡선에서는 다를 수 있음 | `label.py`로 실제 값을 manifest에 기록해 E가 확인. 필요하면 설정의 에피소드 수 조정 |
| Kafka 메시지 크기 | 스냅샷당 약 140행이면 약 80KB(한도 약 1MB 안). 가정이 틀리면 초과 | 단계 4에서 실제 크기 확인, 필요 시 압축·분할 |
| Kafka·Spark 도구 버전 | Kafka 이미지·클라이언트 버전 미확정 | 단계 6 시작 때 확정하고 이 plan에 반영 |
| 주기 실행 | 스케줄러 구성은 범위 밖 | `release`가 멱등이라 스케줄러는 10분마다 명령을 부르기만 하면 된다. 스케줄러 선택(Windows 작업 스케줄러, cron, `k_tms_pipeline`의 Airflow)은 후속 |
| 방출이 멈추는 경우 | 스케줄러가 멈추면 도착이 끊김 | 재개 시 밀린 스냅샷을 한꺼번에 올림(경로·내용은 같고 도착 시각만 달라짐). 장시간 멈추면 알아채도록 로그에 마지막 발행 `run_ts`를 남긴다 |

## Complexity Tracking

| 항목 | 이유 | 더 단순한 대안을 안 쓰는 이유 |
|---|---|---|
| 외부 패키지 추가(Kafka 클라이언트) | Kafka로 발행하려면 필요 | 표준 라이브러리에는 Kafka 클라이언트가 없다. 수집 Lambda가 아니므로 "외부 패키지 금지" 규칙(Lambda 한정)에 해당하지 않지만 이유를 적는다. |
| 슬롯 스냅샷 합치기(`pack.py`) | 파일 수를 실측 규모(하루 48개)로 맞추고 Kafka 메시지 수를 줄임 | 에피소드마다 스냅샷을 만들면 102처럼 파일이 수만 개가 된다. |
| 모양 판정 함수(`classify_shape`) | 생성 곡선이 의도한 모양인지 자동 확인 | 눈으로 확인하면 하루 약 275개를 검증할 수 없다. |
| seed 기반 에피소드(자정 걸침 재생성) | 상태 저장 없이 날짜별로 독립 생성하면서 시간대 편중을 막음 | 하루 안에 가두면 합성 양성이 낮에 몰린다. 상태를 저장하면 backfill 순서와 재생성이 복잡해진다. |
| 102 모듈 복사(새 폴더 `k_tms_synthetic_train/`) | #29 PR과 독립시키고 평가용·학습용을 분리 | 102를 import하면 102 코드가 `main`에 있어야 해서 #29에 계속 의존한다. 복사 대상은 안정적인 모듈이라 갈라질 위험이 작고 출처 커밋을 README에 기록한다. |
