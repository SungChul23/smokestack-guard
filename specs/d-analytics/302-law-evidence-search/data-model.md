# 로컬 문서 검색 데이터 모델

팀 Silver·Gold 스키마가 아닌 D 로컬 검색용 의미 정의다.

## Corpus

- `version`: 이 검색 자료의 식별 버전.
- `as_of`, `verified_on`: `2026-11-12`. 이번 자료는 해당 확인 기준일만 지원한다.
- `review_status`: `local_source_verified`. 팀 운영 승인으로 표현하지 않는다.
- `documents`: 공식 문서 3개. 문서마다 `id`, `title`, `law_number`, `effective_date`, `verified_on`, `source_url`, `raw_sha256`을 가진다.
- `chunks`: 조문 11개. `id`, `document_id`, `article`, `heading`, `text`, `url`, `topics`, `source_text_sha256`을 가진다. `text`는 원문 추출 문자열을 그대로 보존한다. `topics`는 검색용 편집 메타이며 법적 원문이 아니다.
- `limitations`: 별표·서식 본문 미확보, 시설별 적용 판단 미제공, 다른 시행본 미확보.

## 검색 요청

- `question`: 문자열, 공백 제거 후 1~1,000자.
- `asOf`: 문서 기준일. 질문에 다른 날짜가 있으면 충돌을 숨기지 않는다.
- 수치·고유키·권한·Gold 필드는 이 요청에 만들지 않는다.

## 검색 결과

- `status`: `found`, `empty`, `out_of_scope`, `not_found`, `date_unavailable`, `needs_context`, `invalid_input`.
- `message`: 검토한 고정 안내. 원문 밖의 절차·판정·숫자를 생성하지 않는다.
- `evidence`: 관련 원문 후보 최대 4개. 조문과 공식 문서 메타를 포함한다.
- `as_of`, `limitations`: 기준일과 현재 검색 범위.
- 자료 파일 읽기 실패·손상은 UI의 `load_error`로 별도 처리한다. 검색 결과 0개로 바꾸지 않는다.

## 불변 조건

## 2026-11-14 선택적 공식 설명 보강

### 검색 v2

### 2026-11-14 추가 조건 확인

후속 일반 안내 우선 보강: `answer_scope=general` 및 `clarification.optional=true`이면 관련 원문 후보를 먼저 표시하고 선택적 개별 확인은 원문 아래에 접어 둔다. 개별 기한·계산·적용 확정은 필수 조건 확인을 유지한다. 선택적 조건을 입력하면 원래 질문에 대한 확인으로 처리한다.

`conversation_context`는 procedure/report 주제, 문서 기준일·자료 키, 명시/확인한 order_kind/facility_kind/report_kind만 갖는다. 제한된 짧은 서류 후속 질문에서만 읽는다. `context_used`, `resolved_question`으로 재사용 여부를 드러낸다. 지도 선택·시간을 포함하지 않는다. 미확정 값·만료 문맥을 읽지 않으며 문맥이 없으면 구체적인 절차를 확인한다. 임의 대화 이해·장기 저장·모델 호출 기능은 아니다.

공식 설명 구간은 기능 설명 3개를 추가하여 8개다. 법령은 3문서 14조문을 유지한다. 공식 업무편람 첨부 2개는 개정안/과거판 조사 자료로 별도 보존하며 운영 검색 근거에 넣지 않는다.

`search(question, corpus, {asOf, conditions, request_context})`의 조건은 허용한 문자열 필드만 받는다. 문서 종류·자료 범위·명령 종류·시설 유형·보고 유형·일반 규정/개별 판정 범위는 열거형, 수령일·법령 기준일은 유효한 YYYY-MM-DD, 구체화 요청은 1,000자 이하 문자열이다. 원문에 명시된 값과 입력 값이 충돌하면 다시 확인한다. 수령일은 법령 시행본 기준일과 별도로 해석한다.

확인 응답 `clarification`은 flow, fields, missing_fields, confirmed_values, question_context를 가진다. `question_context`는 원래 질문·기준일·자료 버전/구간 해시에 묶인다. `confirmed_conditions`에는 값의 출처가 질문 명시인지 직접 확인인지 기록한다. 질문·기준일·자료가 바뀌면 기존 조건은 폐기한다. 세션 상태는 메모리에서만 유지한다.

일부 입력은 보존하고 빠진 항목만 다시 묻는다. 완료 시 original_question과 resolved_lookup을 구분한다. 명령 종류·수령일·시설 유형을 받더라도 기산일·연장·예외 검증 전에는 법정 마감일을 계산하지 않는다(`deadline_calculated=false`). 근거 미확보·미지원·범위 밖은 추가 입력만으로 해제되지 않는다. 실제 법적 위반·처분을 확정하지 않는다.

법령 조문은 같은 보존 원문에서 검증한 시행규칙 제15·36·52조를 포함한 14개다. 설명 구간은 공개 목록 제공 항목을 추가한 5개다. 공개 목록과 TMS 장비 항목은 source_scope로 구분하며 일반 소개를 API 응답 명세로 보지 않는다.

응답은 기존 status/evidence 외에 documents(문서 메타 조회), clarification_options(명시적으로 새 질문을 선택하는 확인 카드), required_slots/required_tool(지원 도구·조건 안내), blocked(문서 검색에서 실행하지 않는 요청), interpretation_required, retrieval_method를 가질 수 있다. 모든 응답은 llm_called=false이며 생성·벡터 검색이 실행됐다고 주장하지 않는다.

문서가 명시된 조문은 정확한 문서·번호로 조회한다. 문서 종류 없이 조문번호만 주면 확인 카드를 제공한다. 문서 공포번호가 없으면 같은 종류의 다른 문서로 대체하지 않는다. 메타정보 조회의 documents에는 근거 조문 문자열을 만들어 넣지 않는다.

제출자료·내용 검색에서 원문이 같은 문서의 조·항에 적힌 사항을 명시적으로 참조하면, 실제 확보한 그 조문 하나를 함께 읽고 retrieval_hops에 기록한다. 법/영 등 다른 문서 참조는 추정하지 않으며 최대 4개 근거·한 단계만 허용한다. 문서에 적힌 실행 지시는 수행하지 않는다.

`corpus.supplements`는 기존 법령 `as_of=2026-11-12`와 별개로 `verified_on=2026-11-14`, `review_status`, `documents`, `chunks`, `missing_sources`, `limitations`를 갖는다. 설명 문서는 `source_kind=official_guidance`, `effective_date=null`이며 확인일을 시행일로 바꾸지 않는다. 설명 구간은 태그·시작 문자열의 원문 위치와 원본/텍스트 SHA-256을 보존한다.

설명 출처에만 `www.data.go.kr`/`data.go.kr`, `www.keco.or.kr`/`keco.or.kr`의 HTTPS URL을 허용한다. 설명 구간 URL은 해당 문서 URL과 동일해야 한다. 기존 법령 문서의 국가법령정보센터 제한은 그대로다.

미확보 주제는 `id`, `label`, `source_url`을 갖는다. 해당 질문의 결과는 `not_found`와 `missing_sources`이며 공식 설명을 상세 규정의 대용으로 반환하지 않는다. 설명 검색 결과는 `evidence_kind=official_guidance`, 법령과 설명을 함께 찾은 경우 `mixed`다. 근거는 여전히 최대 4개다. 개별 굴뚝의 상태 원인이나 실제 측정 항목은 일반 설명으로 대체하지 않는다.

- 공식 링크는 `https` 및 `www.law.go.kr`/`law.go.kr`만 허용한다.
- 문서 해시와 조문 원문 해시를 검증한다. 사용자의 질문을 코드·HTML·URL로 실행하지 않는다.
- 수치 비율만으로 위반이나 처분을 확정하지 않는다.
- 질문·검색 이력을 파일·브라우저 저장소에 자동 저장하지 않는다.
