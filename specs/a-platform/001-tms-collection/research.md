# Research: TMS 원본 수집 인프라

사후 문서화이므로 미해결 항목(NEEDS CLARIFICATION)은 없다. 구현 과정에서 내린 결정과 그 이유를 기록한다.

## R1. 실행 기반: EventBridge Scheduler + Lambda

- **Decision**: EventBridge Scheduler가 10분마다 Lambda를 비동기 호출한다.
- **Rationale**: 하루 144회, 회차당 수 초 작업이라 상시 서버가 필요 없다. Scheduler는 시간대(`Asia/Seoul`)와 유연 시간 창 OFF를 지원하고, 전용 호출 역할로 권한을 분리할 수 있다.
- **Alternatives considered**: EventBridge Rule(시간대 미지원, UTC 고정), Airflow(B의 로컬 검증용, 상시 운영 비용), EC2 cron(관리 부담).

## R2. `rate(10 minutes)` 대신 `cron(0/10 * * * ? *)`

- **Decision**: cron 식을 쓴다.
- **Rationale**: rate는 스케줄 생성 시각을 기준으로 돌아 실행 분이 :03, :13처럼 어긋난다. cron은 매시 00분부터 10분 단위로 맞아, `run_ts`가 예측 가능한 값이 된다.

## R3. 회차 시각(`run_ts`)은 예정 시각에서 정한다

- **Decision**: Scheduler 입력에 `{"time": "<aws.scheduler.scheduled-time>"}`을 넣고, Lambda가 이를 10분 단위로 내린다.
- **Rationale**: Lambda 비동기 재시도(최대 2회)도 같은 이벤트를 받으므로 같은 경로에 저장된다. 실행 시각을 쓰면 재시도마다 다른 경로가 생긴다.
- **주의**: `jsonencode`는 `<`, `>`를 `<`, `>`로 바꿔 Scheduler 컨텍스트 속성이 치환되지 않는다. 그래서 문자열 리터럴로 쓴다.

## R4. 변경 감지: 응답 바이트 SHA-256

- **Decision**: 응답 원문 바이트의 SHA-256을 직전 값과 비교해, 다를 때만 원문을 저장한다.
- **Rationale**: API는 약 30분마다 갱신되고 호출은 10분마다라, 그대로 저장하면 같은 원문이 3배로 쌓인다. 바이트 해시는 파싱 없이 판단할 수 있다.
- **Alternatives considered**: `mesure_dt` 최댓값 비교(값 일부가 정정되면 놓침), 매번 저장(저장량 3배, Silver 중복 제거 부담).
- **Trade-off**: 응답 순서만 바뀌어도 "변경"으로 저장된다. 보존 관점에서는 안전한 쪽이다.

## R5. `s3:ListBucket`을 주지 않는다

- **Decision**: 수집 역할에 ListBucket이 없다. 상태 파일이 없을 때 생기는 `AccessDenied`는 `NoSuchKey`와 같게 첫 실행으로 처리한다.
- **Rationale**: 수집기는 키를 정확히 알고 있어 목록 조회가 필요 없다. 최소 권한.
- **Risk**: 다른 원인의 `AccessDenied`(정책 오류)도 첫 실행으로 오인해 원문을 매번 저장할 수 있다. 원문이 사라지는 방향은 아니므로 허용한다. 이때 로그에 `{"state": "없음", "code": "AccessDenied"}`가 매번 찍히므로 확인할 수 있다.

## R6. 점검 실패 시 원문은 남기고 상태는 유지

- **Decision**: 저장 → 점검 → (성공 시) 상태 갱신 순서. 점검이 실패하면 예외로 Lambda 실패 처리한다.
- **Rationale**: 이상한 응답도 원인 분석을 위해 보존해야 한다. 상태를 갱신하지 않으면 다음 정상 응답이 반드시 "변경"으로 저장된다.

## R7. 경보: `Errors` + 값 없음 = 경보

- **Decision**: 900초 구간 `Errors` 합 ≥ 1, `treat_missing_data = "breaching"`.
- **Rationale**: 스케줄이 멈추면 Lambda 지표 자체가 없어진다. 값 없음을 경보로 봐야 "호출 중단"을 잡는다. 구간을 수집 주기(10분)보다 길게 잡아 정상 운영 중 빈 구간이 생기지 않게 했다.
- **Limit**: API가 몇 시간째 같은 값을 주는 상황(실행은 정상)은 잡지 못한다. 이는 002 누락률 리포트와 후속 신선도 경보에서 다룬다.

## R8. 상태 backend: S3 + `use_lockfile`

- **Decision**: 상태 버킷 하나를 bootstrap(로컬 상태)으로 만들고, 스택마다 `backend.tf`에 키를 하드코딩한다. DynamoDB 잠금 대신 S3 네이티브 잠금(`use_lockfile = true`)을 쓴다.
- **Rationale**: 팀원이 파일을 주고받지 않고 `terraform init`만으로 연결된다. Terraform 1.10+의 S3 잠금은 별도 테이블이 필요 없다.

## R9. 동시 실행 미고정

- **Decision**: `reserved_concurrent_executions`를 설정하지 않는다.
- **Rationale**: 계정 동시 실행 한도가 10이면 예약 후 남는 비예약 한도가 최소값(10)보다 작아져 설정할 수 없다.
- **Follow-up**: 한도 상향 후 1로 설정한다(상태 파일 경합 방지).
