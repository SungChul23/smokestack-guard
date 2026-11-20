# Research: 대시보드용 K-TMS 관측 RDS 적재

spec의 기본값과 열린 항목을 구현 결정으로 바꾼 기록이다. 형식: 결정 / 이유 / 버린 대안.

## R1. 네트워크: VPC 안 Lambda, S3 게이트웨이 엔드포인트만 쓴다

- **결정**: 적재 Lambda는 앱 프라이빗 서브넷 2개(`tms-app-a`, `tms-app-c`)에 붙인다. 이 서브넷의 라우팅에는 이미 S3 게이트웨이 엔드포인트가 있다(009 R3). NAT·인터페이스 엔드포인트를 새로 만들지 않는다.
- **이유**: RDS는 프라이빗 DB 서브넷에만 있어 VPC 밖에서는 닿지 않는다. NAT는 평소 꺼 두고(월 약 $47/개), 인터페이스 엔드포인트는 서비스·AZ마다 월 약 $7~10이 붙는다. S3 게이트웨이 엔드포인트는 무료다.
- **결과로 생기는 제약**: Lambda 안에서는 **S3 말고 다른 AWS API를 부를 수 없다**(Glue 카탈로그, Athena, SNS, SSM, Secrets Manager, RDS API 모두). 그래서 아래 R2·R3·R4를 정했다.
- **버린 대안**: NAT를 켜 둠(상시 비용, 평소 끄는 운영과 충돌). Secrets Manager·SNS·Glue 인터페이스 엔드포인트(서비스마다 비용, 관리 대상 증가).

## R2. Silver를 읽지 않고, 매일 다시 계산하지 않는다

- **결정**: 관측 표의 정정은 30분 경로(`recent`)만 한다. `recent`는 최근 4시간에 **받은** 스냅샷을 측정 시각과 상관없이 모두 `to_silver`로 바꿔 UPSERT한다. 매일 경로(`daily`)는 관측 행을 쓰지 않고 RDS 안의 SQL로 일일 요약과 매핑 점검만 한다. 다시 채우기(`day`)는 `recent`와 같은 코드로 그 하루의 원본을 처리한다(범위 계산은 008의 `ktms_pipeline.ingest_dates`·`in_range`).
- **이유**:
  - API는 굴뚝마다 "지금 보여 줄 최신 측정"만 준다. 과거 칸의 변화(상태 문구 변경, 확인 중이던 값 채움, 가동을 멈춘 굴뚝의 옛 칸)도 반드시 새 스냅샷으로 들어온다. 새 스냅샷을 빠짐없이 반영하면 관측 표는 최신이 된다.
  - 범위를 4시간으로 겹쳐 읽어 실행이 몇 번 빠져도 다음 실행이 메운다. 긴 공백(RDS 꺼짐, 장애)은 사람이 `backfill`로 메운다.
  - Silver(Iceberg)를 읽으려면 Glue 카탈로그 API가 필요하지만 R1 때문에 부를 수 없다. 원본에서 매일 2일치를 다시 계산하는 것은 위 이유로 얻는 것이 없다.
  - 결과적으로 이 기능은 03:00 Silver 갱신과 완전히 독립이다.
- **정본과 같은지 확인**: SC-003 — 확정(D−2)된 날의 관측(NOx·SOx)을 Silver와 Athena로 비교한다(quickstart §6). 다르면 그 날짜에 빠진 실행이 있었다는 뜻이고 `backfill`로 고친다.
- **버린 대안**:
  - 매일 Silver 최근 2일로 덮어쓰기: Glue API가 필요하고 30분 경로가 이미 같은 정정을 한다.
  - 매일 원본 2일치 재계산: 결과가 30분 경로와 같아 중복이다.
  - NAT를 켜서 Silver 읽기: 개당 월 약 $47이 상시로 들고, RDS를 켤 때마다 NAT도 켜야 하는 의존이 생긴다.

## R3. 실행 구조: Scheduler → Step Functions → Lambda

- **결정**: 두 경로 모두 EventBridge Scheduler가 상태 머신 `tms-dashboard-load`(Standard)를 시작하고, 상태 머신이 다음 순서로 진행한다.
  1. `rds:describeDBInstances`(`tms-db`) — 없으면(`DBInstanceNotFound`) **건너뜀으로 성공 종료**(FR-006·011).
  2. 있으면 엔드포인트 주소를 입력에 넣어 적재 Lambda 호출. 같은 Lambda가 `mode`(`recent`/`daily`/`day`)로 하는 일을 나눈다.
  3. (`daily`) Lambda가 돌려준 처음 본 사업장 이름이 있으면 `sns:publish`(운영 토픽).
  4. 실패하면 Catch → `sns:publish`(운영 토픽) → Fail.
- **이유**: RDS 존재 확인과 SNS 발행은 VPC 밖 서비스 통합으로 해야 한다(R1). RDS는 꺼 두면 인스턴스 자체가 없어지므로(009, `count`) 존재 여부로 판단한다. 주소도 여기서 받으니 스냅샷에서 다시 만들어도 설정을 바꿀 필요가 없다.
- **비용**: 30분 경로 하루 48번 × 상태 전환 약 4번 + 매일 1번 ≈ 월 6,000 전환 → 무료 한도(4,000)를 넘는 부분 약 $0.05/월.
- **시각**: 30분 경로는 `cron(15,45 * * * ? *)` Asia/Seoul. 새 스냅샷 폴더가 :10·:40에 생기므로 5분 뒤다(SC-001 40분 안). 매일 경로는 `cron(20 3 * * ? *)`: 전날 23:30 값의 지연이 끝난 뒤 :15 `recent`가 반영한 결과로 요약하도록 :20.
- **버린 대안**: Scheduler가 Lambda를 바로 호출(RDS가 꺼졌을 때 연결 실패와 진짜 실패를 구분할 수 없고 SNS를 못 보냄). 기존 03:00 상태 머신에 단계 추가(이 기능은 Silver와 무관하고, 008·011 상태 머신을 건드리지 않는 쪽이 안전).

## R4. DB 인증: RDS IAM 인증 (비밀번호 없음)

- **결정**: RDS에 IAM DB 인증을 켠다(`tms-database`의 `iam_database_authentication_enabled = true`). DB 계정 `tms_loader`(적재), `tms_app`(D 앱)을 만들고 `rds_iam` 역할을 준다. Lambda는 boto3 `generate_db_auth_token`으로 15분짜리 토큰을 만들어 TLS로 접속한다. 토큰 생성은 로컬 서명이라 네트워크 호출이 없다.
- **이유**: 비밀번호를 Secrets Manager에서 읽으려면 엔드포인트나 NAT가 필요하다(R1). IAM 인증이면 비밀값 자체가 없다(원칙 II).
- **권한**: Lambda 역할에 `rds-db:connect` — 리소스 `arn:aws:rds-db:ap-northeast-2:952900391026:dbuser:*/tms_loader`. RDS를 스냅샷에서 다시 만들면 리소스 ID가 바뀌므로 인스턴스 부분은 `*`로 둔다(계정 이름으로 좁힘).
- **TLS**: RDS 공용 CA 번들(`global-bundle.pem`)을 패키지에 넣고 인증서를 검증한다.
- **관리자 계정**: `tms_admin`(비밀번호, Secrets Manager)은 그대로 두고, 마이그레이션·초기 적재만 사람이 베스천 터널로 쓴다. 관리자에게 `rds_iam`을 주지 않는다(주면 비밀번호 로그인이 막힌다).
- **버린 대안**: Secrets Manager 인터페이스 엔드포인트(월 비용, 비밀값 관리). 비밀번호를 Lambda 환경 변수에(원칙 II 위반).

## R5. DB 드라이버: pg8000

- **결정**: 순수 파이썬 드라이버 `pg8000`(+ 의존 `scramp`, `asn1crypto`)을 레이어에 넣는다. pandas·numpy는 010과 같은 AWS SDK for pandas 관리형 레이어를 쓴다.
- **이유**: 순수 파이썬이라 Lambda 런타임(x86, Python 3.12)과 빌드 환경 차이에 영향받지 않는다. 30분에 약 4천~2만 행이라 성능이 충분하다.
- **쓰기 방식**: 임시 표에 넣은 뒤 `INSERT … SELECT … ON CONFLICT (stack_key, item, measured_at) DO UPDATE … WHERE (값이 다를 때만)`. 1만 행 단위로 나눈다.
- **버린 대안**: psycopg(바이너리 휠을 Lambda용으로 맞춰야 함). SQLAlchemy(이 규모에 과함).
- **원칙 확인**: 외부 패키지 금지 규칙은 수집 Lambda에만 해당한다(AGENTS.md). 이 Lambda는 수집과 무관하다.

## R6. 보안그룹: 적재용 새 그룹

- **결정**: `tms-network`에 보안그룹 `tms-loader`를 추가한다. 나가는 규칙은 DB 5432(→ `tms-db`)와 443(S3 엔드포인트 접두사 목록)뿐이고, 들어오는 규칙은 없다. `tms-db`에 "5432 ← `tms-loader`"를 추가한다.
- **이유**: 보안그룹은 서로를 참조하므로 한 스택에 모은다(009 R1). 앱 서버 그룹(`tms-app`)을 재사용하면 ALB 규칙까지 따라온다.

## R7. 스택과 코드 위치

- **결정**: 새 스택 `infra/stacks/tms-dashboard-load/`(Lambda, 레이어, 역할, 상태 머신, 스케줄 2개, 로그 그룹)와 코드 폴더 `services/dashboard-load/`(Lambda 진입점, 적재 로직, 마이그레이션 SQL, 실행 명령, 테스트).
- **이유**: 업무 단위로 따로 apply한다(AGENTS.md). 서비스 앱(`dashboard-api`)과 배포 주기·권한이 다르다.
- **다른 스택 변경**: `tms-network`(R6 보안그룹), `tms-database`(R4 IAM 인증 켜기). 둘 다 A의 스택이다.

## R8. 마이그레이션과 초기 적재: 사람이 베스천 터널로

- **결정**: `services/dashboard-load/migrations/NNN_*.sql`을 순서대로 적용하는 명령 `run_dashboard_load.py migrate`. 적용 기록은 DB의 `ops.schema_migrations`에 남겨 같은 파일을 두 번 적용하지 않는다. 사람이 베스천 SSH 터널(`localhost:5433` → RDS)을 열고 `tms_admin`으로 실행한다. `ref` 초기 적재(`load-ref`)도 같은 방식이다.
- **이유**: DDL·계정 생성은 관리자 권한이 필요하고 자주 하지 않는다. Lambda에 관리자 권한을 주지 않는다. 터널은 이미 팀이 DBeaver로 쓰는 경로다(009).
- **버린 대안**: Lambda에 `migrate` 모드(관리자 비밀번호가 필요해 R1과 충돌). Alembic(SQL 몇 개에 과함).

## R9. 사업장 목록 위치

- **결정**: D의 사업장 목록은 원본 버킷 `ref/sites/<버전>.csv`(비공개)에 사람이 올리고, 덮어쓰지 않는다. `load-ref`가 S3나 로컬 파일 경로를 받는다.
- **이유**: 실제 사업장 이름·주소·좌표가 있어 Public 저장소에 넣지 않는다(011의 `_ref_stats`와 같은 방식). 원본 버킷은 퍼블릭 접근이 모두 막혀 있다.
- **열린 것**: D의 파일 형식·컬럼. 받기 전에는 `load-ref`의 입력 계약(contracts §4)대로 D에게 요청한다.

## R10. 매핑 점검 상태

- **결정**: `ops.mapping_report`에 날짜별 점검 결과를 남기고, `ops.unmapped_name`(이름, 처음 본 날, 알림 보낸 시각)으로 같은 이름을 반복해 알리지 않는다(FR-010). Lambda는 새로 처음 본 이름 목록만 돌려주고 SNS는 상태 머신이 보낸다(R3).
- **새 굴뚝**: 아는 사업장의 새 굴뚝 키는 `recent`가 `ref.stack`에 `source = observed`로 바로 추가한다. 사업장 코드는 이름 이력으로 자동 연결되므로 메일 없이 점검 기록에만 남긴다.
- **요약 대상 날짜**: 최근 2일 + 직전 `daily` 이후 관측 행이 바뀐 날짜(`loaded_at` 기준). 늦은 정정이 들어온 과거 날짜의 요약도 다시 맞춘다(FR-009).

## R11. 비용

| 항목 | 추정 |
|---|---|
| Lambda | 30분 경로 약 20초 × 1GB × 하루 48번 + 매일 수십 초 → 월 약 3만 GB-초, 무료 한도(40만) 안 |
| Step Functions | 월 약 6,000 전환 → 약 $0.05 |
| Scheduler | 월 약 1,500번 호출, 무료 한도 안 |
| S3 GET | 30분마다 스냅샷 약 24개 → 월 약 3.5만 GET ≈ $0.01 (다시 채우기는 1회성) |
| RDS·베스천 | 009 비용 그대로(켜 둘 때만). 저장 약 2~2.5GB는 20GB 안 |
| NAT·엔드포인트 | 없음 |

## R12. 테스트

- 순수 함수(적재용 정리, 요약 계산, 범위 계산)는 pandas만으로 단위 테스트한다.
- DB 쓰기·UPSERT·권한은 로컬 PostgreSQL 16(테스트용 컨테이너 또는 CI 서비스 컨테이너)으로 통합 테스트한다. 두 번 적재 결과 동일, 오래된 행 미변경, 상태 행 null, 앱 계정 쓰기 거부를 확인한다.
- Silver와의 일치(SC-003)는 운영 확인(quickstart)으로 한다.
