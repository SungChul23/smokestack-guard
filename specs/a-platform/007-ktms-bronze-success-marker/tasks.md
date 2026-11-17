---

description: "Task list for K-TMS Bronze 확정 표지(manifest, _SUCCESS)와 과거 스냅샷 백필"
---

# Tasks: K-TMS Bronze 확정 표지(manifest, _SUCCESS)와 과거 스냅샷 백필

**Input**: `specs/a-platform/007-ktms-bronze-success-marker/` (plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md)

**Tests**: 자동 테스트를 둔다. 수집 코드 결함은 수집 공백으로 이어지고(원칙 I), plan R8이 사례를 정했다. 테스트를 먼저 쓰고 실패를 확인한 뒤 구현한다.

**실행 주체**: `terraform plan`·`apply`, 백필 `--apply`, AWS 확인은 사람(A)이 한다. 에이전트는 코드·테스트·문서, `terraform fmt`/`validate`, 로컬 pytest까지 한다.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: 다른 파일이라 병렬 가능
- **[Story]**: US1(새 스냅샷 표지), US2(백필), US3(무중단 배포)

## 경로

- 수집 코드: `services/tms-collector/` (`handler.py`, `bronze_marker.py`만 Lambda zip에 들어간다)
- 테스트: `services/tms-collector/tests/`
- 인프라: `infra/modules/scheduled-collector/main.tf`

---

## Phase 1: Setup

- [X] T001 테스트 환경 `services/tms-collector/pyproject.toml` 작성: `requires-python = ">=3.11"`, `dependencies = []`, dev 의존성 `pytest`, `boto3`(로컬 import용), `[tool.pytest.ini_options] testpaths = ["tests"]`, `pythonpath = ["."]`. 런타임 의존성은 없다(Lambda 내장 boto3).
- [X] T002 Lambda zip 제외 목록 `infra/modules/scheduled-collector/main.tf`의 `data "archive_file" "code"` `excludes`에 `"tests/**"`, `"pyproject.toml"`, `"uv.lock"`, `"backfill_markers.py"`, `".pytest_cache/**"`, `".venv/**"` 추가 (research R5). 이유 주석 한 줄.
- [X] T003 [P] CI `.github/workflows/tms-collector.yml`: `services/tms-collector/**`, 이 workflow 파일 변경 시 Python 3.13에서 `pip install pytest boto3` 후 `pytest -q` (working-directory `services/tms-collector`). 기존 `.github/workflows/tms-silver.yml` 형식을 따른다.

---

## Phase 2: Foundational (표지 형식 공용 모듈)

**Purpose**: 수집(US1)과 백필(US2)이 같은 함수로 manifest를 만든다 (research R5).

- [X] T004 [P] `services/tms-collector/tests/conftest.py`: dict 기반 가짜 S3 클라이언트 `FakeS3`
  - `put_object(Bucket, Key, Body, ContentType=None, ChecksumSHA256=None, IfNoneMatch=None)`: `ChecksumSHA256`이 있으면 base64(SHA-256(Body))와 비교해 다르면 `ClientError("BadDigest")`; `IfNoneMatch="*"`이고 키가 있으면 `ClientError("PreconditionFailed")`(HTTP 412). 쓰기 순서를 `self.put_log`에 기록.
  - `get_object` → `{"Body": BytesIO}`, 없으면 `ClientError("NoSuchKey")`; `head_object`, 없으면 `ClientError("404")`.
  - `list_objects_v2` + `get_paginator("list_objects_v2")`(Prefix 필터).
  - 특정 키에서 실패시키는 `fail_on_put = {key: code}` 훅.
  - 가짜 SSM(`get_parameter` → 고정 키). 환경 변수 `BRONZE_BUCKET=test-bucket`, `API_KEY_PARAMETER=/test/key`를 설정한 뒤 `handler`를 import하고 `handler.s3`, `handler.ssm`을 가짜로 바꾸는 fixture.
- [X] T005 [P] `services/tms-collector/tests/test_bronze_marker.py`: `build_manifest`가 data-model.md §2를 따르는지 — `manifest_version` = 1, `files` = 원문·메타 두 개 "이 순서", `sha256`은 "저장된 바이트(gzip·JSON) 기준 소문자 hex", `raw_sha256`은 압축 전 원문 기준, `committed_at` UTC 초 단위 ISO 8601, `backfilled` 기본 false. `checksum_b64`가 S3 `ChecksumSHA256` 형식(base64 of digest)인지. 키 이름 함수(`raw_key`, `meta_key`, `manifest_key`, `success_key`)가 `run_ts` 폴더 아래 경로를 내는지.
- [X] T006 `services/tms-collector/bronze_marker.py` 구현: 상수 `RAW_NAME="snapshot.json.gz"`, `META_NAME="snapshot.meta.json"`, `MANIFEST_NAME="manifest.json"`, `SUCCESS_NAME="_SUCCESS"`, `MANIFEST_VERSION=1`; `sha256_hex(bytes)`, `checksum_b64(bytes)`, 키 함수, `build_manifest(raw_gz, meta_bytes, raw_sha256, committed_at, backfilled=False) -> bytes`(JSON `ensure_ascii=False, indent=2`, UTF-8), `check_folder(...)`는 T019에서. 표준 라이브러리만. T005 통과.

**Checkpoint**: `pytest tests/test_bronze_marker.py` 통과.

---

## Phase 3: User Story 1 - 새로 저장되는 스냅샷에 확정 표지가 붙는다 (P1) 🎯 MVP

**Goal**: 원문이 바뀐 실행이 원문 → 메타 → manifest → `_SUCCESS` → 상태 파일 순으로 쓰고, 실패하면 표지·상태 갱신이 없다.

**Independent Test**: 가짜 S3에서 핸들러를 돌려 네 파일·순서·해시·상태 파일을 확인한다. 배포 뒤에는 quickstart §3.

### Tests for User Story 1

- [X] T007 [P] [US1] `services/tms-collector/tests/test_handler.py` 정상 저장: 이전 상태와 다른 응답 → `put_log` 순서가 원문, 메타, manifest, `_SUCCESS`, 상태 파일. manifest `files[].sha256`이 저장된 바이트와 같고 `backfilled` = false. `_SUCCESS`는 0바이트, `ContentType="application/octet-stream"`. 원문·메타·manifest put에 `ChecksumSHA256`이 있다. 상태 파일 필드는 정확히 `sha256_raw`, `last_changed_at`, `last_checked_at`, `raw_key` 네 개(FR-007). 반환·로그 요약에 `marker: "written"`. (`fetch_snapshot`은 monkeypatch로 고정 응답)
- [X] T008 [P] [US1] 같은 파일, 원문 점검 실패(`resultCode` ≠ 0 또는 건수 불일치): 원문·메타는 있고 manifest·`_SUCCESS` 없음, 상태 파일 변경 없음, `RuntimeError` (FR-005).
- [X] T009 [P] [US1] 같은 파일, 업로드 실패: `fail_on_put`으로 메타 put이 `BadDigest` → 예외, manifest·`_SUCCESS`·상태 파일 없음. `_SUCCESS` put 실패 → 예외, 상태 파일 변경 없음 (FR-001, FR-002).
- [X] T010 [P] [US1] 같은 파일, 원문이 이전과 같음: 새 폴더 없음, 상태 파일은 `last_checked_at`만 바뀜, `marker` 필드 없음 또는 `"unchanged"` (FR-006).
- [X] T011 [P] [US1] 같은 파일, 같은 `run_ts` 재실행(research R4) 세 경우: (a) 폴더에 원문만 있고 `_SUCCESS` 없음 → 다시 써서 네 파일 완성; (b) `_SUCCESS` 있고 manifest `raw_sha256` = 이번 원문 → 파일 put 없음, 상태 파일만 갱신, `marker: "already_committed"`; (c) `_SUCCESS` 있고 다른 원문 → 폴더 파일 put 없음, 상태 파일 변경 없음, 예외 없이 종료, `marker: "skipped_committed_folder"`.
- [X] T012 [P] [US1] 같은 파일, 로그: 요약 JSON에 응답 본문·API 키가 없다(`capsys`로 확인) (FR-008, 원칙 II).

### Implementation for User Story 1

- [X] T013 [US1] `services/tms-collector/handler.py`: `save_snapshot`를 `bronze_marker`를 쓰도록 바꾼다 — 원문·메타 put에 `ChecksumSHA256=checksum_b64(body)`, 메타 이후 점검 결과 반환. 자체 재시도 루프를 두지 않는다(research R2).
- [X] T014 [US1] `handler.py`: `commit_snapshot(prefix, gz, meta_bytes, raw_sha256)` — manifest put(`ChecksumSHA256`) → `_SUCCESS` put(빈 바이트, `application/octet-stream`). B 원안의 오류(`_read`로 쓰기, `s3.put.object`, `json.load(bytes)`, `"uft-8"`, `object-stream`)를 반복하지 않는다.
- [X] T015 [US1] `handler.py`: `find_committed(prefix)` — `head_object(_SUCCESS)`; `NoSuchKey`/`404`/`AccessDenied`(ListBucket 없음)이면 None, 있으면 manifest를 읽어 `raw_sha256` 반환 (research R4, 기존 `load_state`와 같은 오류 처리).
- [X] T016 [US1] `lambda_handler`: 원문이 바뀐 경우 `find_committed` → (b)/(c) 분기, 아니면 저장 → 점검 실패 시 `RuntimeError`(표지·상태 없음) → `commit_snapshot` → `save_state`(필드 변경 없음). 로그 요약에 `marker` 추가. T007~T012 통과.
- [X] T017 [US1] 상수·주석 정리, `ruff`가 있으면 lint 통과, `services/tms-collector/handler.py` 상단 import에 `bronze_marker` 추가.

**Checkpoint**: `pytest -q` 전체 통과. US1만으로도 배포 가능(새 폴더부터 표지).

---

## Phase 4: User Story 2 - 배포 이전 폴더에 표지를 백필한다 (P1)

**Goal**: `--before` 이전 폴더 중 검증 통과 폴더에만 manifest(`backfilled: true`)·`_SUCCESS`를 덮어쓰기 없이 추가.

**Independent Test**: 가짜 S3에 통과·실패 폴더를 섞어 미리보기·적용·재실행 결과를 확인. 실데이터는 quickstart §4.

### Tests for User Story 2

- [X] T018 [P] [US2] `services/tms-collector/tests/test_backfill.py`: data-model.md §5의 순서·사유 코드 그대로 — 통과 폴더는 표지 추가(`backfilled: true`); `raw_missing`, `meta_missing`, `meta_invalid`, `hash_mismatch`, `inspect_fail`, `raw_key_mismatch` 각 1개는 표지 없음·사유 기록; `_SUCCESS` 있으면 `skipped`; `--before` 이후 폴더는 대상 아님(세지 않음); 미리보기는 `put_log`가 비어 있음; 적용 후 다시 실행하면 `marked = 0`; manifest·`_SUCCESS` put은 `IfNoneMatch="*"`; 원문·메타·`_state/latest.json`은 put되지 않음; 412(`PreconditionFailed`)는 `skipped`로 센다.

### Implementation for User Story 2

- [X] T019 [US2] `services/tms-collector/bronze_marker.py`: `check_folder(prefix, raw_gz | None, meta_bytes | None) -> (ok: bool, reason: str | None, raw_sha256)` — data-model.md §5 검사 3~7.
- [X] T020 [US2] `services/tms-collector/backfill_markers.py`: contracts/backfill-cli.md 그대로 — 인자(`--before` 필수 `YYYYMMDDTHHMMSSZ`, `--apply`, `--bucket`, `--prefix`, `--report`, `--profile`, `--region`), `run_ts=` 폴더 나열(파일 단위로 묶기), 대상 필터, `check_folder`, 적용 시 manifest → `_SUCCESS`를 `IfNoneMatch="*"`와 `ChecksumSHA256`으로 put, 요약 한 줄 + `FAILED <폴더> <사유>` 줄, `--report` JSON, 종료 코드 0/1. `main(argv, s3=None)`으로 테스트에서 가짜 S3 주입. T018 통과.

**Checkpoint**: `pytest -q` 전체 통과.

---

## Phase 5: User Story 3 - 수집을 끊지 않고 배포한다 (P1)

**Goal**: 스케줄 유지, 수집 직후 배포, 확인, 실패 시 되돌림.

**Independent Test**: 배포 전후 실행 기록에 빠진 실행 없음, 다음 날 누락률 리포트 정상.

- [X] T021 [US3] `services/tms-collector/README.md`: S3 경로 트리에 `manifest.json`·`_SUCCESS`, 처리 흐름 4~6단계(체크섬·표지·상태 순서), 재시도 표에 "같은 `run_ts` 재실행은 표지 있는 폴더를 다시 쓰지 않음", "백필" 절(명령은 quickstart §4), "배포" 절(수집 직후 apply, 확인 항목, 되돌림).
- [X] T022 [US3] `infra/` `terraform fmt -recursive` + `infra/stacks/tms-collection`에서 `terraform validate` (에이전트, `/mnt/c/terraform/terraform.exe`).
- [X] T023 [US3] (사람) `terraform plan`: 변경이 `module.collector`의 Lambda 코드(zip 해시) 하나뿐인지 확인. 다른 변경이 있으면 멈춘다.
- [X] T024 [US3] (사람) 수집 직후(x2~x5분) `terraform apply`, 배포 시각 UTC 기록.
- [X] T025 [US3] (사람) quickstart §3 확인: 다음 실행 오류 없음·`marker` 필드, 첫 저장 실행 폴더 네 파일, 알람 없음. 실패 시 되돌림.

**Checkpoint**: 새 폴더에 표지가 붙고 수집 실행이 빠지지 않았다(SC-001, SC-002).

---

## Phase 6: 백필 실행과 공유 (US2 실데이터)

- [X] T026 [US2] (사람) `python backfill_markers.py --before <배포 시각>` 미리보기 → 결과 확인(`targets`, `would_mark`, `failed` 사유).
- [X] T027 [US2] (사람) `--apply --report` 실행 → 재실행해 `would_mark=0` 확인. 원문·메타 개수·크기 전후 비교(SC-004).
- [X] T028 [US2] 결과를 `specs/a-platform/007-ktms-bronze-success-marker/quickstart.md` 끝 "실행 결과"에 기록(배포 시각, 대상·표지·실패 수와 사유).

---

## Phase 7: Polish & Cross-Cutting

- [X] T029 [P] `AGENTS.md` "수집 Lambda 규칙": 원본 경로 줄에 `manifest.json`·`_SUCCESS` 추가, "읽는 쪽은 `_SUCCESS`가 있는 폴더만 완성 스냅샷으로 본다(`specs/a-platform/007-…/contracts/bronze-snapshot-folder.md`)" 한 줄.
- [X] T030 [P] `services/tms-missing-rate/README.md`에 "폴더에 manifest·`_SUCCESS`가 추가돼도 계산 방식은 그대로(메타 기준)" 한 줄. 기준 변경은 범위 밖.
- [ ] T031 PR 본문 초안: 원칙 I 공백 위험·완화·되돌림, B 확인 요청(표지 형식, 백필 실행 주체), C에게 읽는 쪽 계약과 적용 시점 안내, `Closes #40`. 사람 확인 뒤 생성.

---

## Dependencies & Execution Order

- Phase 1 → Phase 2 → (Phase 3 US1, Phase 4 US2 코드는 병렬 가능) → Phase 5 배포(US1 코드 필요) → Phase 6 백필(배포 시각 필요) → Phase 7.
- T006 → T013~T016, T019~T020 (공용 모듈).
- T024(배포 시각) → T026 (`--before`).
- 백필(T027)이 끝나야 C가 읽는 쪽을 `_SUCCESS` 기준으로 바꿀 수 있다(범위 밖).

## Parallel Examples

- Setup: T002(인프라)와 T003(CI)은 다른 파일.
- Foundational: T004(conftest)와 T005(모듈 테스트).
- US1 테스트 T007~T012는 같은 파일이지만 서로 독립 사례 — 한 번에 작성.
- US1 구현(T013~T016)과 US2 테스트(T018)는 다른 파일이라 병렬 가능.

## Implementation Strategy

1. **MVP = US1 + US3**: 새 폴더부터 표지가 붙으면 C가 "배포 이후"는 표지 기준으로 읽을 수 있다.
2. 그다음 US2 백필로 과거 폴더까지 채운다.
3. 커밋 단위: Setup·공용 모듈(T001~T006) → 수집 표지(T007~T017) → 백필(T018~T020) → 문서(T021, T029, T030).
