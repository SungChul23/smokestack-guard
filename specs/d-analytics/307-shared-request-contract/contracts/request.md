# 로컬 계약

최초 원문과 버전에 결속된 생성/검증 함수만 사용한다. 입력 JSON은 권한이 아니다.

- format: summary/original/original_and_summary/미확인. extent: excerpt/full_article/all_items/unspecified.
- target: article_text/procedure/topic. 법령 종류를 추측하지 않고 참고 조문을 목표로 바꾸지 않는다.
- 부족 슬롯은 allowlist로 검증한다. 구형 missing_conditions는 재입력 안내만 제공하며 도구 값으로 해석하지 않는다.
- 기준일은 명시된 법령 기준일과 사용자 확인에서만 받는다. 사건·수령 날짜는 contextDates로 보존하고, 역할이 불명확한 날짜나 현행·오늘 요청은 보관 기준일로 자동 대체하지 않는다.
- procedure_kind 등 허용된 부족 슬롯은 원문에 보충한 뒤 다시 형태소 분석하는 카드로 연결한다. 일반 절차의 유형이 미확정이면 관련 문서가 있어도 답변 생성을 보류한다.
- 전체 범위 미확인, 불완전 전문,1채널 혼합 출력은 보류한다. 요약·혼합 출력과 절차 근거를 골라 제공하는 원문 출력에는 독립 검수가 필수다. 직접 지정한 조문 전문은 필수 인용 전체와 원문 완전성이 확인되어야 한다.
- 구형 답변 패킷과 변경된 패킷의 검수 승인은 재사용하지 않는다. 새 계약으로 패킷을 다시 만들고 검수한다.
- 305 계획은 기존 허용 recipe 검증과 원문 조건 결속을 거친 dry-run이다. 이 API는 복합 계획의 문서 단계를 자동 실행하지 않는다. 기존 단일 search_documents 후보 경로의 읽기 전용 검색은 유지한다.

## 흐름 보강

- 명시된 명령/자체개선 두 경로는 ordered_and_voluntary와 stages(plan/report)로 보존한다. 모호한 절차 비교는 한쪽 보고로 축소하지 않는다.
- 답변 패킷의 required_evidence_groups는 경로 및 requirements의 각 세부 단계 근거를 모두 요구한다. 의미 검수와 별개다.
- 판정의 명시적 제외는 분류와 검색이 같은 document-intent 해석을 사용한다. 삭제·비밀·날짜 검사에 앞서 원문을 줄이지 않는다.
- INVALID_MISSING_SLOTS는 사용자에게 새 조건을 요구하는 근거가 아니다. 같은 원문·문맥의 해석기 형식 재시도는 최대1회이며 추가 재시도는 거부한다. 실시간 모델 호출 연결을 뜻하지 않는다.
