# Implementation Plan: 서비스 로그 수집·분석 (CloudWatch → Firehose → OpenSearch)

**Branch**: `65-a-서비스-로그-수집분석-cloudwatch-firehose-opensearch` | **Date**: 2026-11-20 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/a-platform/014-log-opensearch/spec.md`

## Summary

대상 로그 그룹 8개(서버 2, Lambda 6)에 구독 필터를 붙여 Firehose 3개(서버·파이프라인·활동)로 보내고, 공용 변환 Lambda가 CloudWatch 묶음을 줄 단위 문서로 풀어 서비스 이름·수준·JSON 필드를 붙인 뒤 OpenSearch 도메인 `tms-logs`(t3.small.search 1대, 공개 엔드포인트, FGAC)의 하루 단위 인덱스에 넣는다. 실패분은 새 로그 버킷에 둔다. Dashboards는 013 Cognito(Google + `members`)로 로그인한다. 인덱스 템플릿·보관(14일·28일)·역할 매핑·오류 알림·저장 대시보드는 저장소의 정의를 멱등 스크립트로 적용한다. 서버에는 요청 기록과 사용자 활동을 JSON 한 줄로 남기는 미들웨어를 더한다. 28일 약 $41.

## Technical Context

**Language/Version**: Python 3.12(변환 Lambda, 서버), Python 3.11+(설정 스크립트) · Terraform `~> 1.15.0`, AWS provider `~> 6.0`

**Primary Dependencies**: 표준 라이브러리 + boto3/botocore(SigV4 서명). 새 외부 패키지 없음

**Storage**: OpenSearch 인덱스(로그 사본), S3 `smokestack-tms-logs-952900391026`(전달 실패분, 28일). 원본은 CloudWatch Logs(바꾸지 않음)

**Testing**: pytest — 변환 Lambda(묶음 풀기·JSON 펼치기·수준 추정·제어 메시지), 서버 미들웨어(필드·상태 확인 제외·개인 정보 없음), 설정 스크립트(dry-run 출력)

**Target Platform**: OpenSearch Service, Data Firehose, Lambda, CloudWatch Logs 구독 필터, Cognito 자격 증명 풀

**Project Type**: 관측 파이프라인(관리형) + 서버 로그 형식

**Performance Goals**: 로그 → 검색 5분 안(Firehose 버퍼 60초·1MB), 대시보드 검색 10초 안

**Constraints**: 비밀값 없음(IAM·Cognito). 수집 Lambda 실행·스케줄·저장 경로 변경 없음. 원본 버킷에 수명 주기 규칙 추가 없음(로그 실패분은 새 버킷). 28일 비용 $50 이하

**Scale/Scope**: 실제 로그는 하루 수 MB(2026-11-21 확인, research R7), 14일 보관 수백 MB 이하, 디스크 10GB. 엔진 `OpenSearch_2.19`

## Constitution Check

| 원칙 | 판정 | 근거 |
|---|---|---|
| I. 수집 연속성 | 통과 | 구독 필터는 로그 그룹에만 붙는다. 수집 Lambda 코드·역할·스케줄·원본 경로를 바꾸지 않는다. 도메인을 지워도 수집 영향 없음(FR-006·FR-017) |
| II. 비밀값 비공개 | 통과 | 비밀번호 없음(FGAC 마스터 = IAM 역할, Firehose·뷰어 = IAM 역할). 로그 형식 계약이 비밀·개인 정보를 금지(contracts/log-format.md) |
| III. 코드로 만들고 적용은 사람이 | 통과 | AWS 자원은 Terraform. OpenSearch 내부 설정은 저장소 정의 + 멱등 스크립트(사람 실행). 예외: OpenSearch가 만드는 Cognito 앱 클라이언트의 Google 추가(quickstart §4에 기록) |
| IV. 데이터 계약 우선 | 통과 | 서버 로그 형식을 계약으로 고정하고 D와 공유 |
| V. 같은 조건의 정직한 비교 | 해당 없음 | |
| VI. 설명 가능한 결과 | 통과 | 오류 알림·대시보드가 서비스·시각·원문으로 근거를 보여 준다 |

### IAM 권한 (최소)

| 주체 | 권한 | 리소스 |
|---|---|---|
| CloudWatch Logs → Firehose 역할 `tms-logs-cwl` | `firehose:PutRecord(Batch)` | Firehose 3개 |
| Firehose 역할 `tms-logs-firehose` | `es:ESHttpPost/Put/Get`, `es:DescribeDomain*` | 도메인 `tms-logs` |
| | `lambda:InvokeFunction` | 변환 Lambda |
| | `s3:PutObject` 등 | 로그 버킷 |
| 변환 Lambda 역할 | 기본 로그 권한만 | |
| Cognito 뷰어 역할 `tms-logs-viewer` | `es:ESHttp*` | 도메인 `tms-logs` (FGAC가 읽기로 좁힘) |
| OpenSearch → SNS 역할 `tms-logs-sns` | `sns:Publish` | `tms-collector-alerts` |
| OpenSearch Cognito 서비스 역할 | `AmazonOpenSearchServiceCognitoAccess` | |
| 관리자 역할 `tms-logs-admin` | `es:*` | 도메인 (A가 설정 스크립트 실행 때 맡음) |

## Project Structure

### Documentation

```text
specs/a-platform/014-log-opensearch/
├── spec.md  plan.md  research.md  data-model.md  quickstart.md
├── contracts/log-format.md
├── checklists/requirements.md
└── tasks.md
```

### Source Code

```text
infra/stacks/tms-log-search/                 # 새 스택 (opensearch_enabled 스위치)
├── backend.tf  versions.tf  variables.tf  outputs.tf
├── domain.tf          # 도메인, 접근 정책, Cognito 연결, 자격 증명 풀·역할, 관리자·SNS 역할
├── delivery.tf        # 로그 버킷, 변환 Lambda, Firehose 3개, 구독 필터·역할
services/log-search/
├── transform.py       # Firehose 변환 Lambda (CloudWatch 묶음 → 문서)
├── setup_opensearch.py  # 템플릿·ISM·역할 매핑·알림·저장 객체 (멱등, --dry-run)
├── opensearch/        # index-templates/*.json, ism/*.json, roles/*.json, monitors/*.json
├── dashboards/*.ndjson
├── tests/
└── README.md
services/dashboard-api/app/logging_mw.py      # 요청 기록·log_activity (에이전트에도 같은 파일)
services/dashboard-api/app/main.py            # 미들웨어, /api/me·/api/invite 활동 기록
services/dashboard-api/Dockerfile             # --no-access-log
services/dashboard-agent/app/logging_mw.py, main.py, Dockerfile
.github/workflows/log-search.yml              # ruff + pytest
AGENTS.md                                     # 스택·폴더·로그 버킷
```

**Structure Decision**: 새 스택 `tms-log-search`(하는 일 기준 이름)로 묶어 스위치 하나로 켜고 끈다. 다른 스택은 건드리지 않는다(로그 그룹 이름은 고정 문자열로 참조). 서버 코드는 미들웨어 파일 하나를 두 앱에 같은 내용으로 둔다(013 `auth.py`와 같은 방식).

## Complexity Tracking

| 항목 | 필요한 이유 | 더 단순한 대안을 버린 이유 |
|---|---|---|
| 변환 Lambda | 서비스 이름·수준·JSON 필드 | Firehose 기본 메시지 추출은 로그 그룹 이름을 버림 |
| Firehose 3개 | 묶음별 인덱스·보관 기간 | 하나로 모으면 보관 기간을 나눌 수 없음. 시간 요금이 없어 비용 차이 없음 |
| 설정 스크립트 | OpenSearch 내부 설정은 REST API에만 있음 | Terraform OpenSearch provider는 도메인 생성과 같은 apply에서 순서 문제 |
| Cognito 앱 클라이언트 수동 수정 | OpenSearch가 만드는 클라이언트 | Terraform으로 관리 불가(서비스가 만듦) |
