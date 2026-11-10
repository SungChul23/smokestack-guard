# Implementation Plan: K-TMS Bronze 확정 표지(manifest, _SUCCESS)와 과거 스냅샷 백필

**Branch**: `40-a-k-tms-수집-lambda에-bronze-확정-표지manifest-_success-추가-및-과거-스냅샷-백필` | **Date**: 2026-11-10 | **Spec**: [spec.md](spec.md) | **Issue**: #40

**Input**: Feature specification from `specs/a-platform/007-ktms-bronze-success-marker/spec.md`

## Summary

수집 Lambda(`services/tms-collector/handler.py`)가 원문이 바뀐 실행에서 원문·메타를 S3 체크섬으로 확인하며 올리고, 원문 점검을 통과하면 `manifest.json` → `_SUCCESS`를 쓴 뒤 상태 파일을 갱신한다. 같은 `run_ts` 재실행은 완성된 폴더를 다시 쓰지 않는다. 표지 형식은 작은 공용 모듈(`bronze_marker.py`)로 만들고, 같은 모듈을 쓰는 백필 명령으로 배포 이전 526여 개 폴더에 표지를 붙인다. 스케줄은 그대로 두고 수집 직후에 배포한다.

## Technical Context

**Language/Version**: Python 3.13 (Lambda 런타임, 기존과 같음). 백필은 로컬 Python 3.11 이상.

**Primary Dependencies**: 표준 라이브러리 + boto3(Lambda 런타임 내장). 새 외부 패키지 없음. 테스트만 pytest.

**Storage**: S3 `smokestack-tms-raw-952900391026/tms_cleansys/` (원본 경로, 추가만).

**Testing**: pytest + dict 기반 가짜 S3·SSM 클라이언트. CI `.github/workflows/tms-collector.yml`.

**Target Platform**: AWS Lambda `tms-collector` (ap-northeast-2), 로컬 WSL(백필).

**Project Type**: 서버리스 수집 함수 + 1회용 운영 CLI + IaC 소폭 수정.

**Performance Goals**: 저장 실행당 요청 3개 추가(head 1, put 2). 실행 시간 영향 1초 미만(제한 240초).

**Constraints**: 수집 스케줄 유지(원칙 I). 표지가 있는 폴더 불변. 상태 파일 형식 불변. 로그에 응답 본문·키 금지.

**Scale/Scope**: 백필 대상 526개 폴더(2026-10-30 ~ 11-10, 원문 평균 약 60KB, 합계 약 30MB) + 배포 전까지 늘어나는 폴더. 이후 저장 실행은 하루 수십 회.

## Constitution Check

*GATE: Phase 0 전 통과, Phase 1 뒤 재확인.*

| 원칙 | 판단 | 근거 |
|---|---|---|
| **I. 수집 연속성** | ✅ 조건부 (B 확인 필요) | 스케줄·주기 변경 없음. **공백 위험**: 새 코드 결함 시 매 실행 실패. **완화**: 테스트(R8), 수집 직후 배포·다음 실행 확인, 실패 시 되돌림(R7) → 놓치는 실행 최대 1회, 그 슬롯은 다음 실행들이 다시 받음. 원본은 추가만(표지 2개), 완성 폴더 불변(R4), 백필은 조건부 생성으로 덮어쓰기 불가(R6). **B의 확인을 PR에서 받는다.** |
| II. 비밀값 비공개 | ✅ | API 키 처리 변경 없음. 로그 요약에 표지 여부만 추가 |
| III. 코드로 만들고 사람이 적용 | ✅ | Terraform 변경은 zip 제외 목록뿐. apply·백필 `--apply`는 사람이 실행 |
| III. 최소 권한 | ✅ | 수집 역할 권한 추가 없음(체크섬·`head_object`는 기존 `s3:GetObject`/`s3:PutObject`로 충분). 백필은 A의 IAM 사용자로 1회 |
| IV. 데이터 계약 우선 | ✅ | 폴더 계약 `contracts/bronze-snapshot-folder.md`. 읽는 쪽 변경(C)은 백필 공유 뒤 C가 한다 |
| V, VI | 해당 없음 | |
| 운영 제약: 비용 | ✅ | S3 요청 저장 실행당 3개 추가, 백필 1회 약 1,600개 요청·30MB 읽기. 월 $0.01 미만 |
| 운영 제약: 패키지 | ✅ | 수집 Lambda는 표준 라이브러리 + boto3 유지 |

**Phase 1 뒤 재확인**: 데이터 모델·계약에 위반 없음. 통과. 원칙 I의 B 확인은 PR 리뷰 항목으로 남긴다.

## Project Structure

### Documentation (this feature)

```text
specs/a-platform/007-ktms-bronze-success-marker/
├── spec.md
├── plan.md                         # 이 문서
├── research.md                     # R1~R8
├── data-model.md                   # 폴더·manifest·상태 전이·백필 판정
├── quickstart.md                   # 테스트 → 배포 → 확인 → 백필
├── contracts/
│   ├── bronze-snapshot-folder.md   # 읽는 쪽 규칙
│   └── backfill-cli.md             # 백필 명령 인자·출력
├── checklists/requirements.md
└── tasks.md                        # /speckit-tasks
```

### Source Code (repository root)

```text
services/tms-collector/
├── handler.py              # 수정: 저장 흐름에 체크섬·manifest·_SUCCESS·재실행 처리
├── bronze_marker.py        # 새로: manifest 생성, 해시, 키 이름, 백필 판정 (Lambda zip 포함)
├── backfill_markers.py     # 새로: 백필 CLI (zip 제외)
├── pyproject.toml          # 새로: 테스트용 (zip 제외)
├── tests/                  # 새로: pytest, 가짜 S3 (zip 제외)
│   ├── conftest.py
│   ├── test_handler.py
│   └── test_backfill.py
└── README.md               # 수정: S3 경로·처리 흐름·백필

infra/modules/scheduled-collector/main.tf   # 수정: archive excludes에 tests/**, pyproject.toml, backfill_markers.py
.github/workflows/tms-collector.yml          # 새로: pytest
```

**Structure Decision**: 수집 코드와 같은 폴더에 두되 Lambda zip에는 `handler.py`와 `bronze_marker.py`만 들어가게 한다. 누락률 Lambda zip은 바뀌지 않는다.

## 배포 절차 요약

1. PR 리뷰(B 확인 포함) → 머지.
2. `terraform plan` → 수집 함수 코드 1개 변경만 확인.
3. 수집 직후(x2~x5분) apply, 배포 시각 UTC 기록.
4. 다음 실행과 첫 저장 실행 확인 → 실패 시 되돌림(R7).
5. 백필 미리보기 → `--apply` → 재확인.
6. C에게 배포 시각·백필 결과 공유.

## Complexity Tracking

위반 없음.
