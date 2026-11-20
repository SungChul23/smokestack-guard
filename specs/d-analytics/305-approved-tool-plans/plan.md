# 구현 계획: 승인된 단일·복합 도구 실행 계획

**기능**: 305 · **작성일**: 2026-11-14 · [명세](spec.md)  
브랜치 작업 없음. `SPECIFY_FEATURE_DIRECTORY=specs/d-analytics/305-approved-tool-plans`로 기존 Python 3.12 가상환경에서 공식 setup_plan.py를 실행했다. Windows의 python3 별칭은 접근 불가여서 동일 Python 스크립트를 기존 실행 파일로 호출했다. 설치 파일은 수정하지 않았다.

## 요약

기존 분석기를 바꾸지 않고 `approved-plans.js`를 위에 둔다. 등록된 4개 복합 recipe와 단일 도구만 사용한다. `approved-plan-session.js`는 단일 세션 위임과 복합 카드·재검증을 담당한다. 검토 화면은 기존 Kiwi API에 원문만 보내고 브라우저에서 실행 전 계획을 표시한다. 외부 실행기는 없다.

## 기술 환경

- JavaScript CommonJS/브라우저 번들, Node 내장 test/assert, 기존 Python 3.12·Kiwi 0.24.1·루프백 실험실 재사용.
- 새 패키지·스토리지·서버·AWS 비용 없음. 기존 사용자 검수 기록 저장 형식에 plan이 함께 들어간다.
- 대상: `D/dashboard-preview/regional-console/query-router/`, 기존 `D/query-router-lab/manual-review-20261114/`.
- 상한: 복합 recipe당 정확히 2단계. 각 단계 입력은 기존 도구 계약만 허용한다. 임의 SQL/코드/엔드포인트는 없다.
- 성능: 결정적 계획 작성은 모델/네트워크를 추가하지 않는다. 실제 응답 성능을 운영 기준으로 주장하지 않는다.

## 원칙 점검

수집기·스케줄·원본 불변, 비밀값/자격증명 미사용, 인프라 변경 없음, Silver·모델 계약 미정의, 원문/기대 보존, 결과 출처·실패 상태 공개. 사전/설계 후 모두 위반 없음. D 로컬 도구 명령 계약이며 데이터 계약 변경이 아니다.

## 구조와 단계

1. `capability-catalogue.js`: 현재 단일 6개·복합 4개·대기 능력·자료 미보유 목록. 비교/추세/지역 집계/모델 평가 등은 목록에 있더라도 실행 가능으로 켜지 않는다.
2. `approved-plans.js`: `planQuestion`, `validateToolPlan`, `reviewPlanResults`. 등록 recipe의 도구 순서/공유 조건/상한을 검사하고 각 단계를 기존 `validateCandidate`로 검증한다. 원문 가드가 먼저다. 명확한 고정 복합 표현만 분리하고 나머지는 기존 해석 후보를 유지한다.
3. `approved-plan-session.js`: 단일은 기존 tool-session을 위임한다. 복합 슬롯은 shared 또는 단계 ID로 구분하고 원문·확정 조건을 유지한다. 5분 TTL·문맥 fingerprint·옵션 ID를 검사한다. 해석안은 명시 조건 보존 검사와 최종 확인을 거친다.
4. `build-workbench.cjs`, `manual-review-20261114/review.js`: 계획 단계·허용 조합·공통 조건 카드를 표시한다. 기존 8766 흐름과 메인 관제 실행은 바꾸지 않는다.
5. `tests/query-router/approved-plans.test.cjs`, 고정 복합 사례와 브라우저 검사. 원문 분류·계획 구조·카드 보완·부분 실패 검증을 구분한다.

## 검증·한계

단위는 먼저 실패를 확인하고 구현한다. 기존 전체 단위·기존 검토 브라우저·새 복합 사례를 검사한다. 과거 해석 후보가 승인 recipe로 바뀐 사례는 의도한 변화로 별도 기록하며 원 기대를 수정하지 않는다. 결과 대조기는 합성된 테스트 응답을 사용하며 운영 인증/실행 결과 진위를 보장하는 서비스로 표현하지 않는다. 추정 법적 결론·근거 없는 모델 원인·kg 환산을 새로 제공하지 않는다.
