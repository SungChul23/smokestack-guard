# Research: 학습용 합성 K-TMS 데이터 AWS Bronze 적재

## R1. 메시지 경로 없이 예약 실행 → Lambda → S3 직접

- **결정**: EventBridge Scheduler → Lambda → S3. Kafka·Kinesis·Firehose 없음.
- **이유**: 30분에 완성된 스냅샷 1개(gz 약 2KB). 버퍼, 변환, 여러 수신처가 필요 없고, 합성은 seed로 같은 바이트를 다시 만들 수 있어 메시지를 보관할 이유가 없다. 실측 수집과 같은 운영 모양이다.
- **대안**: EC2 안 Kafka(t3.medium 상시 월 $35~40, 서버 운영), MSK(월 $100대 이상), Kinesis Streams + Lambda(샤드 1개 월 약 $11, 적재 Lambda가 결국 같은 일), Firehose(실측과 같은 폴더·`_SUCCESS` 순서를 못 지킴).
- **보고서 표기**: B의 Kafka → Spark → Bronze 경로는 파일 모드와 바이트가 같음을 B가 확인했다(#57). 운영은 직접 적재, 스트리밍은 같은 결과를 내는 대안 경로.

## R2. 상태 없는 재계산

- **결정**: 실행마다 대상 슬롯이 속한 날짜 D에 대해 `daily.episodes_started_on(D−1) + (D)` → `pack.pack_day(D)`로 48슬롯 스냅샷을 메모리에서 만들고, 쓸 슬롯만 골라 쓴다.
- **이유**: 에피소드는 (시작 날짜, 성분, 모양, 번호)로 정해진 seed에서 나오고 하루보다 짧아, 이틀치만 보면 어떤 슬롯이든 재현된다. 저장소(DB·파일)가 필요 없고 재처리·백필·정기가 같은 코드다.
- **측정(2026-11-17, 가짜 참조 통계 800행)**: 에피소드 550개 2.2초, 48슬롯 파일 0.2초, 슬롯당 117~136행, gz 2.1~2.3KB.

## R3. 패키징

- **결정**: Lambda zip = `lambda_handler.py` + `synth_train/` 중 필요한 모듈(`__init__`, `plan`, `schedule`, `stats`, `daily`, `assemble`, `shapes`, `scenarios/__init__`, `scenarios/trajectory`, `pack`, `snapshot`, `writer`, `s3_sink`, `generate`) + `config/daily.json`. Terraform `archive_file`의 `source` 블록으로 파일을 하나씩 넣는다.
  - `generate`는 에피소드 태그(`manifest_row`)용. Kafka를 import하지 않는다.
  - `daily.json`은 Terraform이 `jsonencode(yamldecode(file("daily.yaml")))`로 만든다. 그래서 PyYAML이 필요 없고, B가 yaml을 고치면 다음 apply에 반영된다.
  - 진입점은 `plan.load_config`(yaml) 대신 json을 읽는다. 그 외 B 함수는 그대로 부른다.
- **레이어**: 010과 같은 `AWSSDKPandas-Python312:18`(numpy·pandas·boto3).
- **대안**: PyYAML을 zip에 넣기(빌드 단계가 생김), 컨테이너 이미지(과함).

## R4. 쓸 슬롯 고르기

- **정기**: 예정 시각 `T`(Scheduler `<aws.scheduler.scheduled-time>`, 없으면 현재 시각). `run_ts`가 `(T − 180분, T]`인 슬롯 중 `_SUCCESS`가 없는 것. 대상 날짜는 `run_ts − 70분`(측정 시각)의 KST 날짜들이며 최대 2개(자정 근처).
- **백필**: `from`~`to` 각 날짜의 48슬롯 중 `run_ts ≤ 현재 시각`이고 `_SUCCESS`가 없는 것. 범위 상한 31일(한 번 실행 15분 안).
- **확정 확인**: `head_object(<prefix>/_SUCCESS)`. 있으면 건너뜀(007 규칙). 없으면 B의 `write_files_s3`로 전부 다시 쓴다(같은 바이트).
- **에피소드 태그**: 날짜 D의 슬롯을 처음 쓸 때 `_manifest/D.jsonl`이 없으면 `generate.manifest_row`로 만들어 쓴다(시작 날짜가 D인 에피소드만, B 계약 §6과 같음).

## R5. 실패 대비

| 층 | 설정 |
|---|---|
| Scheduler | 재시도 최대 3회, 최대 이벤트 나이 1시간, DLQ = SQS `tms-synthetic-train-dlq` |
| Lambda 비동기 호출 | 재시도 2회, 최대 이벤트 나이 1시간, 실패 목적지 = 같은 SQS |
| 알람 | SQS `ApproximateNumberOfMessagesVisible` ≥ 1 (5분) → 운영 SNS `tms-collector-alerts` |
| 점검 | 별도 스케줄 매일 06:00 KST, 입력 `{"mode":"check"}` → 전날 48슬롯의 `_SUCCESS` 확인, 모자라면 운영 SNS로 슬롯 목록 발행 |
| 자기 회복 | 정기 실행의 180분 창 |

- SQS는 일반(Standard), 보관 14일. 순서·중복은 `run_ts` 폴더와 `_SUCCESS` 건너뛰기로 해결해 FIFO가 필요 없다.
- 두 DLQ 메시지 모양이 다르다: Scheduler DLQ는 원래 입력을 본문으로, Lambda 실패 목적지는 `requestPayload` 안에 원래 입력을 담는다. 재처리 명령은 두 모양을 모두 받는다(contracts §3).
- 점검 시각 06:00: 전날 마지막 슬롯(23:30)의 `run_ts`는 00:40이고, 재시도·DLQ 재처리 여유를 둔다.
- 매일 갱신(03:00)은 최근 2일을 다시 계산하므로, 이틀 안에 채운 슬롯은 자동 반영된다.

## R6. 권한 (최소)

| 주체 | 권한 | 범위 |
|---|---|---|
| Lambda | `s3:PutObject`, `s3:GetObject` | `tms_synthetic_train/ingest_date=*`, `tms_synthetic_train/_manifest/*` |
| 〃 | `s3:GetObject` | `tms_synthetic_train/_ref_stats/*` |
| 〃 | `s3:ListBucket` | 버킷, 접두어 `tms_synthetic_train/` 조건 |
| 〃 | `sns:Publish` | 운영 토픽(점검 결과만) |
| 〃 | 로그 쓰기 | 자기 로그 그룹 |
| 〃 | `sqs:SendMessage` | DLQ(실패 목적지용) |
| Scheduler 역할 | `lambda:InvokeFunction`, `sqs:SendMessage` | 이 Lambda, DLQ |

- `tms_cleansys/`, `bronze/`, `silver2/` 권한 없음. 삭제 권한 없음. `_ref_stats/`는 읽기만(덮어쓰기는 사람이, 버전 이름으로).

## R7. 참조 통계 위치

- **결정**: 원본 버킷 `tms_synthetic_train/_ref_stats/<stats_version>.csv`(예: `ref-1030-1110.csv`). 사람(B 또는 A)이 한 번 올린다.
- **이유**: 합성 전용 접두어 아래라 권한을 묶기 쉽고, `_`로 시작해 테이블이 아니다. `ops/`는 Terraform이 올리는 파일만 두는 규칙이라 쓰지 않는다. 실제 굴뚝명이 있어 저장소·Terraform 상태에 넣지 않는다.
- **버전 확인**: 진입점은 설정의 `stats_version`과 파일 이름, 파일 안 `stats_version` 열을 비교해 다르면 쓰기 전에 실패한다.

## R8. 버전 고정

- `daily.yaml`의 `run.generator_version`, `run.stats_version`이 meta에 들어간다. 설정이나 통계를 바꾸면 버전을 올리고 `specs/b-collection/103.../` 또는 이 spec의 quickstart 기록표에 적용 시작 날짜를 적는다.
- 확정된 과거 슬롯은 다시 쓰지 않으므로, 과거를 새 기준으로 다시 만들려면 버전별 새 경로나 지우고 다시 쓰기가 필요하다. 이건 B·E와 정할 일로 남긴다(범위 밖).

## R9. 하류 연결 (US4, C 대기)

- 008 상태 머신 입력에 `source`(`ktms` 기본 | `ktms_synth`)를 추가하고, Glue 잡 인자 `--source_prefix`, `--silver_table`, `--ml_ready_table`, `--data_source`, `--runs_prefix`로 넘긴다. 008의 `check_source_prefix`가 C의 `read_bronze`에 `prefix` 인자가 생길 때만 합성 경로를 연다.
- **빠진 인자(2026-11-17 확인)**: ML-ready 잡(`glue_ktms_ml_ready.py`)에 `--data_source` 인자가 없어 합성도 자동으로 `ktms`가 붙는다. 인자를 추가해 `to_ml_ready(silver, data_source=…)`로 넘긴다(A 코드, C 규칙은 이미 인자를 받음). Silver 잡의 `--source_prefix`·`--silver_table`, ML-ready 잡의 `--silver_table`·`--ml_ready_table`은 이미 있다.
- **경로 인자(2026-11-17 결정)**: C를 기다리지 않고 A가 `ktms.read_bronze`·`_keys`에 `prefix` 인자를 추가했다(기본값 그대로, 판정 규칙 변경 없음). C 코드 변경이므로 PR에서 C 리뷰를 받는다. 008의 `check_source_prefix`는 이 인자가 생기면 자동으로 합성 경로를 연다.
- 합성 매일 갱신은 별도 스케줄(03:30 KST, 실측 갱신과 Glue 동시 실행이 겹치지 않게)로 같은 상태 머신을 `source=ktms_synth` 입력으로 시작한다.
- 010 검사 입력: `check_table=tms_silver2.ktms_synth_ml_ready`, `expect_source=ktms_synth`, `real_table=tms_silver2.ktms_ml_ready`. 검사 Lambda 권한에 합성 테이블 읽기를 추가한다.
- Glue 역할 권한: 합성 원본 읽기(`tms_synthetic_train/*`), 합성 테이블 쓰기(`silver2/ktms_synth*`).

## R10. CI

- 새 워크플로 `tms-synthetic-train.yml`: `k_tms_synthetic_train/**` 변경 시 Python 3.12로 `pip install pandas numpy pyyaml pytest` 후 `pytest -q`. B의 테스트가 처음으로 CI에서 돈다.
