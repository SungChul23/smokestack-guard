# Feature Specification: 404 SageMaker 학습 Job·아티팩트 관리

**관련 이슈** [Issue #20](https://github.com/SungChul23/smokestack-guard/issues/20) · **상태** 기존 구현과 남은 검증을 재정리

## User Scenarios & Testing

### US1 SageMaker 학습 Job·아티팩트 관리 (P1)

모델별 학습 실행과 입력·결과를 추적하고 기존 아티팩트를 보호한다.

**인수 조건** Job과 S3 결과 URI를 연결하고 실패 시 불완전한 로컬 모델 디렉터리가 공개되지 않는다.

## Requirements

- **FR-001** 서울 리전에서 한 Job에 한 모델을 실행하며 입력·Role·출력·실행 제한을 기록한다. 기본 review_only와 명시적 제출을 구분한다.
- **FR-002** `model.joblib`, `metrics.json`, `metadata.json`을 모두 저장한 뒤 최종 모델 디렉터리를 공개하며 기존 결과를 덮어쓰지 않는다.
- **FR-003** Job 이름·태그·메타데이터와 모델 버전을 연결한다. 결과의 S3 버킷 정책과 실제 제출 인자를 구분해 기록한다.

## Success Criteria

- **SC-001** Job과 S3 결과 URI를 연결하고 실패 시 불완전한 로컬 모델 디렉터리가 공개되지 않는다.

구현 근거와 보류 사항은 [plan.md](plan.md), 작업 상태는 [tasks.md](tasks.md)를 참조한다.
