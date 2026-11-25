# Feature Specification: 407 시나리오 B 성능 평가·국내 외부 검증

**관련 이슈** [Issue #58](https://github.com/SungChul23/smokestack-guard/issues/58) · **상태** 기존 구현과 남은 검증을 재정리

## User Scenarios & Testing

### US1 시나리오 B 성능 평가·국내 외부 검증 (P1)

국내 실측에서 경보 성능을 검증하고 시나리오 A와 같은 조건에서 비교한다.

**인수 조건** 공통 국내 Test의 행 키·Label 일치를 증명하며, 다른 기간이나 반복 사용한 평가 결과는 독립 최종 평가와 구별한다.

## Requirements

- **FR-001** 국내 실측 Validation에서만 F2 임계값을 선택하고 Test에 고정한다. 행 지표는 [403](../403-model-evaluation/spec.md)를 따른다.
- **FR-002** A/B 비교는 405의 고정 스냅샷·기간·적격 조건·Feature 순서와 동일 평가 키를 사용한다. 각 모델의 기존 확정 임계값을 적용한다.
- **FR-003** AP·Precision·Recall·F2·FPR·혼동행렬과 커버리지를 구분해 비교한다. 사건 지표가 있다면 평가 가능 분모와 거짓 경보 단위를 함께 기록한다.

## Success Criteria

- **SC-001** 공통 국내 Test의 행 키·Label 일치를 증명하며, 다른 기간이나 반복 사용한 평가 결과는 독립 최종 평가와 구별한다.

구현 근거와 보류 사항은 [plan.md](plan.md), 작업 상태는 [tasks.md](tasks.md)를 참조한다.
