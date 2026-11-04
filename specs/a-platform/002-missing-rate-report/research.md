# Research: Bronze 슬롯 누락률 일일 리포트

## R1. 별도 Lambda + 모듈 확장 재사용

- **Decision**: 수집 Lambda와 다른 함수로 배포하고, `scheduled-collector` 모듈에 변수를 추가해 재사용한다.
- **Rationale**: 주기(10분 vs 하루), 권한(API 키 vs 목록 조회), 시간 제한, 재시도, 알람 의미가 모두 다르다. 한 함수에 핸들러를 둘 수 없다. 모듈 재사용으로 로그 그룹·역할·스케줄·알람 구성을 일관되게 유지한다.
- **Alternatives considered**: (a) 수집 Lambda zip에 파일만 추가 — 호출되지 않음, (b) 스택에 리소스 직접 작성 — 약 150줄 중복, (c) 별도 스택 — 버킷·토픽 참조를 원격 상태로 넘겨야 함.
- **Guard**: 새 변수 기본값 = 현재 동작. 구현 관문으로 `terraform plan`에서 `module.collector` 변경 0건을 확인한다.

## R2. 누락 알림: 예외 대신 SNS 직접 발행

- **Decision**: 자동 실행에서 누락이 있으면 함수가 SNS 토픽에 요약 메시지를 발행하고 정상 종료한다. `Errors` 알람은 계산 실패에만 쓴다.
- **Rationale**:
  - B의 원래 방식(누락 시 `RuntimeError`)은 메일이 "tms-missing-rate-errors ALARM"뿐이라 무엇이 빠졌는지 알 수 없고, 계산 실패와 구분되지 않는다(spec Edge Cases).
  - 예외 방식이면 Lambda 비동기 재시도가 누락 계산을 반복한다(재시도 0으로 막을 수는 있음).
  - 직접 발행하면 메일 본문에 날짜·누락 수·슬롯 목록·리포트 경로를 담을 수 있다.
- **Alternatives considered**: 커스텀 지표(`MissingSlots`) + 지표 알람 — 메일에 슬롯 목록이 없고 알람이 하나 더 필요. 나중에 대시보드가 필요해지면 추가 검토.
- **Cost**: `sns:Publish` 권한 하나와 환경 변수 `ALERT_TOPIC_ARN`이 추가된다.

## R3. 하루 1회 함수의 Errors 알람 설정

- **Decision**: `treat_missing_data = "notBreaching"`, `period = 86400`, `evaluation_periods = 1`, 임계값 Sum ≥ 1.
- **Rationale**: 001의 설정(`breaching`, 900초)을 그대로 쓰면 실행이 없는 23시간 59분 동안 항상 경보 상태가 된다. 하루 구간으로 보면 실패한 날은 경보, 다음 날 정상 실행되면 OK로 돌아간다.
- **Trade-off**: 스케줄이 멈춰 이 함수가 아예 안 도는 경우는 알람이 잡지 못한다. 그 경우 리포트가 생기지 않으므로 SC-001(매일 리포트 존재)로 확인하며, 수집 자체는 001 알람이 지킨다.

## R4. 비동기 재시도 0

- **Decision**: `aws_lambda_function_event_invoke_config.maximum_retry_attempts = 0`.
- **Rationale**: 실패 원인이 권한·시간 초과면 재시도해도 같은 결과다. 반복 실행은 같은 실패 알람을 겹치게 할 뿐이다(FR-011). 복구는 수동 백필로 한다.
- **Note**: EventBridge Scheduler 자체의 재시도 정책은 "호출 전달 실패"에만 적용되므로 기본값을 유지한다.

## R5. 실행 시각 09:00 KST

- **Decision**: `cron(0 9 * * ? *)`, `Asia/Seoul`.
- **Rationale**: 관측된 API 반영 지연이 약 2시간이라, 전날 23:30 슬롯은 새벽 1–2시에 나타난다. 09:00이면 충분한 여유가 있고, 업무 시작 시각에 결과를 볼 수 있다.

## R6. 권한 범위

- **Decision**: `ListBucket`(조건 `s3:prefix` = `tms_cleansys/*`), `GetObject`(`tms_cleansys/*`), `PutObject`(`reports/missing_rate/*`), `sns:Publish`(토픽 1개).
- **Rationale**: 원본 경로에 쓰기 권한이 없으므로 코드 실수로도 원본을 바꿀 수 없다(FR-012). `ListBucket`이 있으므로 없는 객체는 `NoSuchKey`로 응답되어, 코드의 "없음" 처리와 맞는다.
- **Note**: 목록 조회 prefix는 `tms_cleansys/ingest_date=…/` 형태라 조건 `tms_cleansys/*`에 포함된다.

## R7. 시간 제한과 메모리

- **Decision**: 180초, 512MB.
- **Rationale**: 정상 운영 시 하루 계산은 UTC 이틀치 약 96개 폴더의 메타 + 원문 GET과 gzip 해제·JSON 파싱이다. 원문 한 개는 약 3,400건 JSON이다. 첫 실행 로그의 소요 시간과 메모리 사용량으로 조정한다.
- **Backfill**: 하루당 처리 시간이 대략 같으므로, 한 번의 수동 호출은 7일 이하로 나눠 실행한다.

## R8. B 코드에서 바꾸지 않는 것

- 슬롯 판정: "정상 원문의 최신 `mesure_dt`가 그 슬롯"이라는 방식. 10분 호출이 30분 갱신보다 촘촘하므로 정상 운영에서는 모든 슬롯이 한 번은 최신값으로 나타난다. 30분 넘게 수집이 끊긴 경우에만 빠지며, 그것이 바로 잡아야 할 누락이다.
- 폴더 상태 분류(`ok`, `inspect_fail`, `meta_missing`, `raw_missing`)와 집계 범위(상태 수는 대상 날짜 폴더만, 수집된 슬롯은 이틀치 전체).
- 실측 확인: `mesure_dt` 형식 `YYYY-MM-DD HH:MM`(KST)이 슬롯 문자열 형식과 같다(2026-11-03 실제 응답).
