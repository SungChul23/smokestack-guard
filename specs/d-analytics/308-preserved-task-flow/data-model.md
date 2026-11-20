# 데이터 모델

- TaskFlow: version, root, conditions, binding. root는 rootQuestion, mode, tasks와 필요한 경우 stages를 가진다. 각 task는 id/kind/span/text를 보존한다. span은 원문 substring과 정확히 일치해야 한다.
- DocumentTask: search_documents, 원문 구간, topic, 필요한 문서/시설/기준일, ready/found/not_found/needs_context/read_failed 상태.
- CaseTask: case_verdict, 원문 구간, unsupported와 고정 한계 안내. 시설별 위반·지연 판단을 계산하거나 모델에 위탁하지 않는다.
- ChildRequest: root binding, 문서 task ID와 span, 확인 조건, 실제 검색 질문·요청 계약. 검색·패킷·초안 전달에서 검증한다.
- RootResult: tasks별 결과와 overall partial/needs_context/not_found. 문서 성공이어도 case unsupported를 숨기지 않는다.
- Input: 확인할 슬롯과 값만 허용. 알 수 없는 필드·법령/시설 기본값·타 request의 선택은 거부한다.

조건 키는 `lawAsOf`, `document_identity`, `facility_kind`, `procedure_kind`, `comparison_scope`, `topic`으로 제한한다. `unknown` 응답은 기본값으로 대체하지 않고 검색 전 미지원으로 종료한다. 명령 이행 수리를 자체개선으로 임의 해석하지 않는다. `stages`는 계획서/보고/양쪽을 구분하며 출력 형식도 문서 child에 보존한다.

읽기 실패 시 `lastDocumentInput`에 저장된 동일 원문·기준일·확인 조건·질문 맥락을 한 번만 재사용한다. 모델 형식 재해석 재시도와 구분한다. 취소·만료·권한·자료 변경 후에는 재시도하지 않는다. `retrieval_executed`는 실제 검색 시도 여부이며 미지원/조건 미확정은 검색한 것으로 표시하지 않는다.

RequestContract.target은 필요한 경우 `requiredTopics`와 `formComparison`을 추가로 가진다. 전자는 원문에 명시된 기록/공개자료의 필수 근거 주제 목록, 후자는 비교할 서식 번호 목록이다. 검색기의 `target_coverage.required_groups`와 답변 패킷의 `required_evidence_groups`는 복합 주제의 각 근거를 보존한다. 원문에 없는 주제·번호를 채우지 않는다.

조건 검사 보강의 MeaningSelections는 단일 ToolSession 내부 상태다. `exceed_definition`, `quantity_kind`, `period_summary`의 허용 카드 값만 담으며 모델 후보의 필드는 아니다. Readiness는 도구 필수 인자·부족 의미·사용자 선택·검사 상태와 `executed:false`를 보유한다. 기존 문서 TaskFlow 조건과 서로 대체하지 않는다. 다단계 계획의 미확정 의미는 원문 보충으로 처리하고 의미 값을 임의의 도구 인자로 넣지 않는다.
