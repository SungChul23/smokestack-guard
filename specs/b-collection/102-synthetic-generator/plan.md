# Implementation Plan: K-TMS 합성 데이터 생성기 (평가·시연용)

**Branch**: `29-k-tms-synthetic` | **Date**: 2026-11-09 | **Spec**: [spec.md](spec.md) | **Issue**: #29

**Input**: Feature specification from `specs/b-collection/102-synthetic-generator/spec.md`

## Summary

실측 통계에서 정상 시계열을 만들고 시나리오 S-01~S-09를 끼워 넣어, **실측 API 응답과 같은 모양의 합성 스냅샷**(`snapshot.json.gz`)을 합성 전용 경로(`tms_synthetic/…`)에 만든다. 현재 Silver 코드(`silver/ktms.py`의 `to_silver`)가 그대로 읽을 수 있어야 하며, 실측 Bronze 경로(`tms_cleansys/`)에는 쓰지 않는다.

생성기는 `k_tms_synthetic/`의 로컬 명령줄 도구다. AWS 리소스·Kafka·Spark는 만들지 않는다. 시나리오마다 기대 결과를 **생성 전에** 파일로 쓰고, 자동 점검(`validate`)이 생성 파일을 다시 읽어 대조한다.

## Technical Context

**Language/Version**: Python 3.12 (저장소 `pyproject.toml`은 `>=3.10`)

**Primary Dependencies**: 표준 라이브러리 + `numpy`·`pandas`(저장소 기존 의존성에서 오는 numpy) + **`pyyaml`(신규, 아래 사유)**. 업로드가 필요할 때만 `boto3`(기존). 수집 Lambda용 "외부 패키지 금지" 규칙은 이 도구에 적용되지 않는다.

**Storage**: 로컬 폴더에 실측과 같은 레이아웃으로 쓴다(기본 `k_tms_synthetic/out/`). 선택적으로 합성 경로로만 업로드(MinIO `bronze` 버킷 또는 S3). 입력 통계 `ref_stats.csv`는 저장소에 커밋하지 않는다.

**Testing**: `pytest` (저장소 기존). 단위 테스트 + 생성 결과를 `to_silver`에 통과시키는 통합 테스트.

**Target Platform**: 개발자 로컬(Windows/macOS/Linux). CI 없음.

**Project Type**: 단일 프로젝트(라이브러리 + 명령줄)

**Performance Goals**: 에피소드 11개 생성이 1분 안에 끝남 (에피소드당 288스냅샷, 파일 수 약 3,000개)

**Constraints**: 실측 경로 쓰기 금지, 같은 설정(seed)이면 바이트 단위로 같은 결과, 비밀값 파일·코드 금지, 외부 호출 없음(통계는 미리 뽑은 CSV)

**Scale/Scope**: 평가·시연용 에피소드 11개, 합성 배출구 에피소드당 1~2개

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| 원칙 | 판정 | 근거 |
|---|---|---|
| I. 수집 연속성 | ✅ | 수집·실측 Bronze를 건드리지 않는다. 쓰기 대상은 합성 경로뿐이며, 쓰기 함수가 `tms_cleansys/` 아래 경로를 거부한다(테스트로 확인). |
| II. 비밀값 비공개 | ✅ | 코드에 키가 없다. 업로드 시 MinIO·AWS 자격은 환경 변수로만 받고 로그에 쓰지 않는다. |
| III. 코드로, 적용은 사람이 | ✅ 해당 없음 | AWS 리소스를 만들지 않는다(Terraform 불필요). 업로드는 사람이 실행한다. |
| IV. 데이터 계약 우선 | ✅ | 항목(`items[]`)은 실측과 같아 새 필드가 없다. 새로 정의하는 것은 합성 경로와 정보 파일뿐이며 [contracts/](contracts/)에 적는다. Silver가 합성 경로를 읽는 방법은 C와 합의한다(spec Assumptions). |
| V. 같은 조건의 비교 | ✅ | 합성은 평가·시연용이며 학습·성능 비교에 쓰지 않는다. 학습용은 별도 spec. |
| VI. 설명 가능한 결과 | ✅ | 정보 파일이 배출구 코드 ↔ 에피소드·시나리오·참조 배출구·통계 버전을 남기고, 기대 결과 파일이 판정 근거를 보존한다. |
| 비용 | ✅ | 로컬 실행. 업로드 시 S3 약 3,000 PUT, 월 0.01달러 미만(업로드를 하는 경우). |
| 외부 패키지 | ✅ 사유 있음 | `pyyaml`: 사람이 쓰고 다른 사람이 검수하는 설정·기대 결과를 읽기 쉬운 형식으로 두기 위해. 대안(JSON·TOML)은 주석·가독성이 떨어져 검수에 불리. |

설계 후 재점검: 통과. 위반 없음 (Complexity Tracking 불필요).

## 설계 결정 (Phase 0 결과)

| # | 결정 | 이유 | 검토한 대안 |
|---|---|---|---|
| D1 | 이벤트가 아니라 **스냅샷** 단위로 만든다. 모양은 `response.header` + `response.body.items[]` | 현재 Silver가 이 모양을 읽는다. 계획서의 Kafka·Spark 경로는 현재 구조에 없다. | 이벤트 + Kafka(계획서) |
| D2 | 저장 경로는 `tms_synthetic/episode=<ID>/ingest_date=…/hour=…/run_ts=…/` | 실측 경로와 분리. 에피소드별 폴더라 깨진 파일(S-07)이 나머지 읽기를 막지 않고, 에피소드 단위로 읽을 수 있다. | 실측과 같은 경로(오염 위험), 에피소드 구분 없는 하나의 경로(S-07이 전체를 막음) |
| D3 | 스냅샷은 10분 간격, `mesure_dt`는 30분 격자. 합성은 기본 지연 0이라 각 스냅샷의 `mesure_dt` = 그 시각을 30분으로 내린 값 | 실측의 반복 구조를 재현. 기본 지연 70분은 만들지 않는다(spec FR-015). | 30분 간격 스냅샷(실측과 다름) |
| D4 | 난수는 `numpy` PCG64, 에피소드마다 `SeedSequence(seed, 에피소드 번호)`로 분리 | 에피소드를 바꿔도 다른 에피소드가 변하지 않고, 같은 설정이면 같은 결과 | 전역 난수 하나(순서 의존) |
| D5 | 정상 구간은 AR(1) + 거부 샘플링(재시도 상한 1,000회, 초과하면 실패) | 값을 잘라 맞추지 않는다(spec FR-009) | 값 자르기(분포가 왜곡됨) |
| D6 | 궤적 이어 붙이기: AR(1)은 시간을 뒤집어도 같은 분포이므로, **궤적 첫 값에서 시간 역방향**으로 앞 구간을, 마지막 값에서 정방향으로 뒤 구간을 만든다 | 앞뒤 구간이 궤적과 자연스럽게 이어지고 덮어쓰기가 필요 없다 | 구간을 만든 뒤 덮어쓰기(경계가 튐) |
| D7 | 궤적 시나리오(S-02~S-05)의 참조 조건에 `|첫 값 − 평균| ≤ 2σ`를 더한다 (구현에서 후보 수를 보고 조정) | 평균에서 너무 멀면 앞 구간이 스스로 "상승"이 되어 시나리오의 의미가 바뀐다 | 조건 없음 |
| D8 | 점검은 **생성된 파일을 다시 읽어** 수행하고, `to_silver`를 import해 Silver 결과도 대조한다 (S3 불필요: `to_silver`는 DataFrame 함수) | 생성기와 점검이 같은 메모리 값을 공유하지 않아 독립적 | 메모리 값 비교(순환 검증) |
| D9 | 설정·기대 결과는 YAML, 시나리오별 파일(`expected/S-xx-E.yaml`) | 생성 전에 쓰고 다른 사람이 검수 | 문서(md)만 |
| D10 | 업로드는 별도 명령으로 분리하고 합성 경로만 허용 | 생성(안전)과 쓰기(공유 저장소)를 분리 | 생성 시 자동 업로드 |

## Project Structure

### Documentation (this feature)

```text
specs/b-collection/102-synthetic-generator/
├── plan.md              # 이 파일
├── data-model.md        # 엔티티·설정·정보 파일 필드
├── quickstart.md        # 생성 → 점검 → Silver 확인 순서
├── contracts/
│   └── synthetic-layout.md   # 합성 경로·스냅샷·정보 파일 계약
├── checklists/requirements.md
└── tasks.md             # /speckit-tasks 에서 생성
```

### Source Code (repository root)

```text
k_tms_synthetic/
├── README.md
├── requirements.txt              # pyyaml
├── config/
│   └── config.yaml               # 시드, 에피소드 개수, 참조 선택 조건
├── expected/
│   └── S-01-E.yaml … S-09-E.yaml # 생성 전에 쓰는 기대 결과 (에피소드별)
├── data/                         # ref_stats.csv (커밋 안 함)
├── out/                          # 생성 결과 (커밋 안 함)
├── synth/
│   ├── __main__.py               # 명령줄 진입점 (generate / validate / upload)
│   ├── stats.py                  # ref_stats.csv 읽기, 참조 후보 걸러내기
│   ├── plan.py                   # 설정 → 에피소드 계획 (시나리오, 참조, 시작 시각, seed)
│   ├── episode.py                # AR(1) 곡선, 거부 샘플링, 궤적 이어 붙이기
│   ├── scenarios/                # 시나리오별 주입 함수 (trajectory, strings, defects)
│   ├── snapshot.py               # 항목(items) 직렬화, 스냅샷·메타·확정 표지 만들기
│   ├── schedule.py               # 10분 간격 run_ts, mesure_dt 격자
│   ├── disturb.py                # S-07 결함, S-08 중복, S-09 지연
│   ├── writer.py                 # 로컬 쓰기 (실측 경로 거부), 업로드
│   └── validate.py               # 파일 재읽기, 합격 기준, 기대 결과 대조, to_silver 확인
└── tests/
```

**Structure Decision**: 이슈에서 정한 `k_tms_synthetic/` 폴더에 단일 프로젝트로 둔다. 실행은 `k_tms_synthetic/`에서 `python -m synth ...`. 저장소 루트의 `src/smokestack_guard/silver/ktms.py`는 읽기 전용으로 import한다(`PYTHONPATH=../src`).

`.github/CODEOWNERS`에 `/k_tms_synthetic/` 담당(B)을 한 줄 추가해야 한다(AGENTS.md 규칙). `.gitignore`에는 `k_tms_synthetic/out/`, `k_tms_synthetic/data/`를 추가한다.

## 구현 순서 (tasks의 뼈대)

| 단계 | 내용 | 완료 기준 |
|---|---|---|
| ① | `ref_stats.csv` 확정, 참조 후보 확인 | 후보 수가 spec 기준과 같음 |
| ② | S-01, 스냅샷 직렬화, `validate` | S-01 기대 결과·합격 기준 통과, `to_silver`가 읽음 |
| ③ | S-02~S-05 궤적 주입 | 시나리오별 기대 결과 통과 |
| ④ | S-06~S-09 문자열·결함·중복·지연 | 시나리오별 기대 결과 통과(콤마 숫자는 알려진 Silver 불일치로 표시) |
| ⑤ | 통계를 `train-v1`로 교체 (11/12 이후) | 생성기 버전·통계 버전 기록 |
| ⑥ | 합성 경로 업로드 + Silver 읽기 경로 지정(C와 합의) | 합성 경로를 Silver가 읽음 |

## 미결·위험

- **콤마 숫자**: 현재 Silver는 `"1,047.55"`를 `other`로 처리한다. S-06의 기대는 "숫자로 파싱"이므로 점검에서 **알려진 불일치**로 표시되며, Silver 수정은 C와 합의한다.
- **잘린 JSON**: 현재 `read_bronze`가 멈춘다. S-07은 별도 에피소드 폴더에 두고 점검은 파일 단위로 JSON 오류를 기대 결과로 확인한다.
- **참조 후보 조건(D7)**: 후보가 너무 줄면 σ 배수를 조정한다.
- **합의 필요**: Silver의 읽기 경로 지정, 콤마 숫자 파싱(C). `.github/CODEOWNERS` 추가(B, 합성 폴더).
