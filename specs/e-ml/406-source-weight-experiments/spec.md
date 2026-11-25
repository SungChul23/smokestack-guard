# Feature Specification: 406 출처별 가중치 및 모델 실험

**관련 이슈** [Issue #58](https://github.com/SungChul23/smokestack-guard/issues/58) · **상태** 기존 구현과 남은 검증을 재정리

## User Scenarios & Testing

### US1 출처별 가중치 및 모델 실험 (P1)

분류 모델에서 국내 실측 행의 상대 가중치 효과를 분리해 검증한다.

**인수 조건** 각 실행의 모델 ID·실제 설정, 출처별 행 수·양성률·가중치 합 비중과 아티팩트를 추적한다.

## Requirements

- **FR-001** N2-C scale_pos_weight=10, S2-C=5. 대만:국내 실측:국내 합성 기준 A=1:1:1, B=1:5:1, C=1:10:1.
- **FR-002** 출처별 sample_weight는 Train에만 적용한다. 양성의 상대 가중치는 출처 행 가중치와 scale_pos_weight가 중첩된다. Validation/Test는 무가중이다.
- **FR-003** 모델·실험당 독립 Job과 결과 경로를 쓰고, 6개 계획을 실행 완료로 간주하지 않는다.

## Success Criteria

- **SC-001** 각 실행의 모델 ID·실제 설정, 출처별 행 수·양성률·가중치 합 비중과 아티팩트를 추적한다.

구현 근거와 보류 사항은 [plan.md](plan.md), 작업 상태는 [tasks.md](tasks.md)를 참조한다.
