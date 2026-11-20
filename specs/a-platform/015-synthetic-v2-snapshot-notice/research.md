# Research: 합성 데이터 v2 전환과 학습 스냅샷 알림

## R1. 적재는 같은 Lambda, 코드만 v2

- **Decision**: `tms-synthetic` 스택의 Lambda `tms-synthetic-train`을 그대로 두고 zip 내용만 v2 코드로 바꾼다. 진입점(`lambda_handler.py`)은 `snapshot.TRAIN_ROOT`를 읽으므로 경로·manifest·참조 통계 위치가 자동으로 `tms_synthetic_train_v2/`가 된다. 스택의 `local.root`만 `tms_synthetic_train_v2`로 바꿔 IAM 쓰기 범위·설명을 맞춘다.
- **확인**: v2 코드 + 우리 진입점으로 테스트 252개 통과(2026-11-20 임시 폴더). 실패는 우리 테스트의 v1 경로 하드코딩 1건(`test_bytes_match_file_mode`)뿐 → 경로를 `lh.MANIFEST_PREFIX`로 바꾼다.
- **zip 모듈 목록**: v2에서 새로 생긴 `real_events.py`·`scripts/`는 진입점이 import하지 않아 목록에 넣지 않는다(`test_terraform_zip_module_list_is_enough_to_import`가 확인).
- **v1 보존**: B의 `writer.check_prefix`가 v1 경로 쓰기를 거부하고, IAM도 v2만 허용한다. v1 객체는 지우지 않는다(원본 버킷 규칙).

## R2. 참조 통계는 사람이 v2 경로로 복사

- **Decision**: `s3://…/tms_synthetic_train/_ref_stats/ref-1030-1110.csv` → `tms_synthetic_train_v2/_ref_stats/ref-1030-1110.csv`를 A가 `aws s3 cp`로 복사한다(실제 굴뚝명 포함, 저장소·에이전트가 다루지 않음). 버전 이름이 같아 설정은 바꾸지 않는다.
- **순서**: 복사 → apply. 반대로 하면 첫 정기 실행이 참조 통계 없음으로 실패하고 DLQ로 간다(다시 채우기로 메워짐).

## R3. 다시 채우기 = 기존 backfill, 기간 나눔

- **Decision**: 10/30~오늘(약 23일)을 `{"mode":"backfill","from":…,"to":…}`로 실행한다. Lambda 제한 시간 900초 안에 들어가게 7일씩 4번(011 quickstart와 같은 방식). 완성 표시가 있는 슬롯은 건너뛰므로 겹쳐도 안전.
- 이어서 `check`를 몇 날짜에 돌려 48슬롯을 확인한다.

## R4. Silver는 같은 표를 v2 원본으로 다시 계산

- **Decision**: `tms-silver`의 합성 원본 경로(`local.synth_source_prefix`, 상태 머신 정의의 `source_prefix`)를 `tms_synthetic_train_v2`로 바꾼다. apply 뒤 `run_ktms.py backfill --source synth --from 2026-10-30 --to <D−2>`로 Silver 5일 묶음 → ML-ready 전체를 다시 계산하고, 계약 검사를 한 번 실행한다(008·011과 같은 절차).
- **Rationale**: `overwrite_range`가 범위를 커밋 한 번으로 교체해 새 스냅샷이 생긴다. 범위가 합성 기간 전체라 최신 버전에 v1 행이 남지 않는다. v1은 이전 스냅샷(시간 여행)과 S3 원본으로 남는다.
- **확인 쿼리**: `SELECT count(DISTINCT stack_code) FROM tms_silver2.ktms_synth_ml_ready WHERE stack_code LIKE '%-OTHER-%'` = 0.
- **Glue 읽기 권한**: 합성 Silver 잡 역할의 원본 읽기(`ReadSynthBronze`)도 같은 로컬 값을 쓰므로 함께 바뀐다.

## R5. 학습 스냅샷 알림: 실행 기록에서 읽는 예약 Lambda

- **Decision**: 새 Lambda `tms-training-snapshot-notice`(표준 라이브러리 + boto3, VPC 밖)를 매일 **05:00 KST** Scheduler로 부른다. 실행 기록만 읽어 메일 본문을 만들고 새 SNS 토픽 `tms-training-snapshots`에 발행한다.
- **스냅샷 고르는 법** (출처마다):
  1. 계약 검사 기록(`silver2/_runs/ktms_ml_ready_check/`) 중 최근 7일, `table`이 그 출처의 ML-ready 표이고 `result = passed`인 것 → ML-ready 스냅샷 = 검사 기록의 `snapshot_id`, 확정 범위 = `range`.
  2. Silver 스냅샷 = 그 ML-ready 실행(`ml_ready_run_record`)이 시작하기 전에 끝난 같은 출처의 마지막 성공 Silver 실행 기록(`silver2/_runs/ktms` 또는 `ktms_synth`)의 `snapshot_id`. ML-ready 잡이 그때의 최신 Silver를 읽었기 때문이다(손으로 다시 계산한 경우에도 맞음).
  3. 실행 날짜(KST)별 최신 하나씩, 최근 3개.
- **Rationale**: 스냅샷 ID가 이미 기록에 있어 Athena가 필요 없고(비용·지연 없음), 상태 머신을 고치지 않는다. 03:00·03:30 갱신과 검사(보통 30분 안)가 끝난 뒤인 05:00이면 그날 결과가 들어 있다.
- **Alternatives**: 상태 머신 끝에 알림 단계(출처마다 두 통이 됨, 정의·테스트 변경 큼), Athena `$snapshots` 조회(검사 통과 여부를 모름).
- **확정 범위 표기**: 검사 기록의 `range`(매일 실행은 최근 이틀) 대신, 학습에 쓸 범위 = 출처 첫날 ~ (실행일 − 2일)로 적는다(008 규칙). 첫날은 실측 `2026-10-30`, 합성 `2026-10-30`(설정값).

## R6. 수신 주소는 SSM 파라미터 한 곳, 저장소에 없음

- **Decision**: 수신 주소 목록을 SSM `/tms/notice/training-snapshot-emails`(StringList)에 사람이 등록하고, Terraform이 apply 때 읽어 `aws_sns_topic_subscription`(email)을 맞춘다. 받는 사람이 확인 메일의 링크를 눌러야 구독된다.
- **Rationale**: 저장소는 공개라 코드·tfvars에 개인 이메일을 쓸 수 없다(AGENTS.md). 처음에는 `TF_VAR`로 받게 했지만 apply마다 넣어야 하고 빠뜨리면 구독이 지워져 헷갈린다(사용자 의견, 2026-11-20). SSM 한 곳에 고정하면 apply할 때 따로 넣을 것이 없다.
- 주소는 SSM과 상태 파일에 남는다(비밀이 아닌 개인 정보).

## R7. 메일 형식

- 제목: `[tms] 학습 스냅샷 2026-11-22 · 실측 확정 ~11-20 · 합성 확정 ~11-20`
- 본문: 출처별 표(실행일, 결과, Silver 스냅샷, ML-ready 스냅샷), 읽기 예시 2줄, 주의(합성은 Train에만, `data_source='ktms_synth'`). 자세한 형식: contracts/notice-format.md.
- SNS 이메일은 텍스트 본문이라 고정폭 표 대신 줄 단위로 쓴다.

## R8. 전환 순서와 공백

1. 참조 통계 복사 → 2. `tms-synthetic` apply(v2 적재 시작) → 3. 다시 채우기 → 4. `tms-silver` apply(합성 원본 v2, 알림 Lambda·토픽) → 5. Silver 다시 계산·검사 → 6. 확인 → 7. E에게 공지.
- 2~5 사이 03:30 합성 갱신이 돌면: 4 이전이면 v1 원본으로 최근 이틀을 계산(무해, 5에서 덮임), 4 이후·5 이전이면 v2 원본 최근 이틀만 v2(5에서 전체가 맞춰짐). 같은 날 몰아서 하면 된다.
