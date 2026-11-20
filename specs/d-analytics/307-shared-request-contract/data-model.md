# 데이터 모델

- RequestContract document-request-1: originalQuestion, version, target(kind/procedure/referenceRole), output(format/extent/ambiguous), asOf, dateAmbiguous, contextDates(value/role), provenance, binding. binding은 변조·혼선 검사에 쓰며 인증 수단이 아니다.
- MissingSlot: 허용 코드와 taskId. 값은 채우지 않고 알 수 없는 코드/작업은 거부한다.
- SearchRequest: 원문·기준일·검증된 RequestContract. 원문 불일치·변조 계약은 거부한다.
- AnswerPacket: request_contract, 출처별 source_manifest, coverage, required_original_quote_ids, original_source_complete를 binding에 포함한다. 요청 절차의 직접 근거가 없는 관련 문서만으로 인용 목록을 만들지 않는다.
- Draft: summary/original/original_and_summary. 전문은 모든 필수 원문ID, 혼합은 segment.kind=original/summary 두 채널이 필요하다. 숫자·출처·결속 검증은 의미 검수와 별개다.
- Plan: 기존305 버전/recipeId/steps 검증을 보존한 계획이며 실행 권한이 아니다.

후속 흐름 필드: 두 일반 절차의 `target.procedure=ordered_and_voluntary`, `target.stages=plan/report`와 답변 패킷의 `required_evidence_groups[].requirements[]`. 모호한 비교는 `procedure_comparison_unresolved`로 보류한다. 형식 재해석은 같은 세션의 `interpretationRetry`에 원문·허용 슬롯·최대1회 제한을 담는다.
