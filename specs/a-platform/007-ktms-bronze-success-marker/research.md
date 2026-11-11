# Research: K-TMS Bronze 확정 표지와 백필

## R1. 업로드 무결성 확인: S3 체크섬

- **Decision**: 원문·메타·manifest는 `put_object(..., ChecksumSHA256=<base64 SHA-256>)`로 올린다. S3가 받은 내용의 SHA-256을 계산해 다르면 업로드를 거부한다(`BadDigest`). 다시 내려받아 비교하지 않는다.
- **Rationale**: 같은 확인을 요청 1번으로 한다. B 원안의 "올린 뒤 다시 읽어 비교"는 요청이 두 배이고, 원안 코드는 그 부분(`s3.put.object`)이 동작하지 않는다. `ChecksumSHA256`은 botocore 1.27(2022)부터 지원되어 Lambda Python 3.13 런타임 boto3로 쓸 수 있다. 추가 IAM 권한은 필요 없다.
- **Alternatives**: 업로드 후 `get_object`로 다시 읽어 비교 → 요청 2배, 시간 증가. `ContentMD5` → MD5라 manifest(SHA-256)와 해시가 달라 두 번 계산해야 한다.

## R2. 업로드 재시도

- **Decision**: 별도 재시도 루프를 두지 않는다. botocore 기본 재시도(일시 오류·스로틀)에 맡기고, 그래도 실패하면 예외로 실행을 실패시킨다.
- **Rationale**: 실패하면 상태 파일이 갱신되지 않아 다음 실행(10분 뒤)이 새 폴더에 다시 저장한다. API는 한 슬롯(30분)을 보통 3번 보여 주므로 한 번 실패해도 데이터는 남는다(002 누락률 리포트가 확인). 코드가 단순해 수집 Lambda의 결함 위험이 줄어든다.
- **Alternatives**: B 원안처럼 3회 루프 + 1·3초 대기 → botocore 재시도와 겹치고, 체크섬 거부(`BadDigest`)는 같은 바이트로 다시 보내도 결과가 같아 의미가 적다.

## R3. 표지 쓰기 순서와 실패 처리

- **Decision**: 원문 → 메타 → (원문 점검 통과 시) `manifest.json` → `_SUCCESS` → 상태 파일. 어느 단계든 예외가 나면 이후 단계를 하지 않는다. 점검 실패는 지금처럼 원문·메타를 남긴 뒤 `RuntimeError`.
- **Rationale**: 읽는 쪽은 `_SUCCESS`만 본다. `_SUCCESS`가 마지막 파일이면 표지가 있는 폴더는 항상 네 파일이 다 있다. 상태 파일을 맨 마지막에 두면 표지가 없는 폴더는 다음 실행에서 다시 저장된다(001 동작 유지).

## R4. 같은 `run_ts`로 재실행될 때 (Lambda 자동 재시도)

- **Context**: 수집 Lambda는 실패 시 AWS 기본값으로 최대 2회 자동 재실행되고, 같은 이벤트 시각을 받아 **같은 `run_ts` 폴더**에 저장한다(001 README). 지금도 재실행은 같은 경로에 다시 쓴다.
- **Decision**: 저장 전에 그 폴더의 `_SUCCESS`를 확인(`head_object`)한다.
  - **없으면**: 지금처럼 그 폴더에 쓴다. 앞 시도는 표지가 없어 미완성이므로 다시 써도 읽는 쪽에 영향이 없다.
  - **있고 manifest의 `raw_sha256`이 이번 원문과 같으면**: 파일을 다시 쓰지 않고 상태 파일만 갱신한다. (표지까지 쓰고 상태 파일 저장에서 실패한 경우)
  - **있고 다르면**: 완성된 폴더를 덮어쓰지 않는다. 경고를 남기고 상태 파일도 갱신하지 않은 채 정상 종료한다. 다음 예약 실행이 새 폴더에 저장한다.
- **Rationale**: 표지가 있는 폴더는 절대 바뀌지 않는다는 약속(FR-009)을 지킨다. 세 번째 경우에 데이터를 잃지 않는 이유는 R2와 같다. `head_object`는 기존 `s3:GetObject` 권한으로 된다(객체가 없으면 `ListBucket`이 없어 `403`이 오는데, 상태 파일과 같은 방식으로 "없음"으로 처리한다).
- **Alternatives**: 조건부 쓰기(`IfNoneMatch="*"`) → 2024-08 이후 botocore가 필요해 Lambda 런타임 boto3 버전에 따라 동작을 장담할 수 없다. 백필(로컬 최신 boto3)에서는 쓴다(R6). 재시도를 끄기(`maximum_retry_attempts = 0`) → 일시 오류 복구 수단이 줄어 수집 공백 위험이 커진다.

## R5. 코드 구조: 표지 로직을 작은 모듈로

- **Decision**: `services/tms-collector/bronze_marker.py`에 순수 함수(manifest 생성, SHA-256·base64, 표지 키 이름, 백필 판정)를 두고, `handler.py`와 백필 스크립트가 함께 쓴다.
- **Rationale**: 수집 시점 manifest와 백필 manifest가 같은 함수로 만들어져 형식이 어긋나지 않는다. `handler.py`는 import 때 환경 변수를 읽어 백필에서 그대로 import하기 어렵다.
- **패키징**: Lambda zip은 `services/tms-collector/` 전체를 묶는다(제외: zip, `__pycache__`, `README.md`). 테스트·백필 스크립트가 zip에 들어가지 않게 모듈의 `excludes`에 `tests/**`, `pyproject.toml`, `backfill_markers.py`를 추가한다. 누락률 Lambda zip은 해당 파일이 없어 내용이 바뀌지 않는다.

## R6. 백필

- **Decision**: `services/tms-collector/backfill_markers.py`. A가 WSL에서 본인 IAM 사용자로 실행한다.
  - 기본은 미리보기(쓰지 않음). `--apply`일 때만 쓴다.
  - `--before <UTC 시각>`(배포 시각) 필수. 그 이전 `run_ts` 폴더만 대상.
  - 폴더마다: 원문·메타 존재 → 원문을 풀어 SHA-256 = 메타 `sha256_raw` → 메타 `inspect.ok` → 메타 `raw_key`가 그 폴더 → 통과 시 manifest(`backfilled: true`)·`_SUCCESS`.
  - 쓰기는 `IfNoneMatch="*"`(없을 때만 생성)와 `ChecksumSHA256`. 이미 있으면 S3가 412로 거부하므로 덮어쓰기가 원천적으로 불가능하다.
  - 결과: 대상·추가·건너뜀·실패 수, 실패 폴더별 사유. `--report`로 JSON 저장.
- **Rationale**: 526개 폴더, 원문 평균 약 60KB라 전체 읽기 약 30MB, 몇 분이면 끝난다. 미리보기 기본값으로 실수를 막는다.
- **Alternatives**: Lambda나 Glue로 실행 → 1회 작업에 리소스를 새로 만들 이유가 없다.

## R7. 배포와 되돌림 (원칙 I)

- **Decision**:
  1. `terraform plan`에서 바뀌는 것이 `tms-collector` 함수 코드(zip 해시)뿐인지 확인한다. 스케줄·알람·역할 변경이 있으면 apply하지 않는다.
  2. 수집 직후(매시 x2~x5분)에 apply한다. 다음 실행(x0분)까지 5분 이상 여유를 둔다.
  3. 다음 실행 로그(`changed`, `marker`)와 알람을 확인한다. 원문이 바뀌는 실행(보통 30분 안)에서 폴더에 네 파일이 있는지 확인한다.
  4. 실패하면 `git revert` 후 apply해 이전 코드로 되돌린다(1~2분). 놓치는 실행은 최대 1회이고, 그 슬롯은 다음 실행들이 다시 받는다(R2).
- **Rationale**: 스케줄을 끄지 않고(FR-016) 결함 영향을 1회 실행으로 제한한다.

## R8. 테스트

- **Decision**: `services/tms-collector/tests/`에 pytest. S3·SSM은 dict 기반 가짜 클라이언트로 대신한다(외부 패키지 추가 없음, dev 의존성은 pytest만). CI는 `.github/workflows/tms-collector.yml`.
- **사례**: 정상 저장(네 파일·해시·순서), 점검 실패(표지 없음·상태 미갱신·예외), 메타 업로드 실패(표지 없음·상태 미갱신), 원문 같음(새 폴더 없음), 재실행 R4의 세 경우, 백필(통과·각 실패 사유·이미 있음·미리보기·재실행 0건).
