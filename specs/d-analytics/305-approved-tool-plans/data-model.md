# 로컬 계획 정보

- **Capability**: ID, 제공 결과, 상태(현재 분석 가능/정의 대기/연결 대기/자료 미보유), 필수 조건, 한계.
- **ToolPlan**: version=`approved-plans-v1`, recipeId, steps. 미등록 필드 금지. recipeId는 등록된 값만 허용한다.
- **Step**: id=`s1` 또는 `s2`, candidate, dependsOn. 미등록 필드 금지. 단일은 1단계, 복합은 정확히 2단계. 도구·순서·의존성은 recipe와 일치해야 한다.
- **SharedSlot**: recipe가 공유한다고 정한 entity/time/pollutants/operation만 해당 단계 모두에 반영한다. dual_pollutants에서는 pollutants를 공유하지 않고 dual_statistics에서는 operation을 공유하지 않는다.
- **PlanSession**: 원문, 분석 시 문맥, TTL=300000ms, 입력 권한 fingerprint, 최신 카드 ID, original plan, LLM 모양 해석 여부·확인 상태. 현재 실행 권한은 항상 false.
- **StepResult**: stepId, status(success/no_results/error/blocked_dependency), sourceRef, applied. 테스트 응답은 합성이라고 명시한다. 관측/문서 성공에 출처, 화면 변경 성공에 applied=true와 요청 조건 일치가 필요하다.

상태: 입력 → 해석 후보/조건 확인/자료 부족/미지원/차단 → 준비 완료. 결과 대조는 준비 완료 계획의 테스트 응답에 대해서만 별도로 수행한다. 실행 또는 원본 쓰기 단계는 없다.
