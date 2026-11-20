# 내부 데이터 표현

이 문서는 303의 브라우저 내부 표현이다. Silver/Gold·운영 API·모델 결과 스키마가 아니다.

## RequestContext

- `request_id`: 탭 내 고유 문자열. 새 제출 시 증가하는 sequence와 연결한다.
- `question`: 문자열, 정규화 후 1~1000자. HTML/명령으로 평가하지 않는다.
- `received_at`: 시간대가 있는 실제 질문 시각. KST 달력 해석에 사용한다.
- `selected_site_id`, `selected_stack_id`: 기존 카탈로그 내부 ID 또는 null. 소속 관계를 검증한다. 지도 공간 선택 `site`와 분석 선택 `selectedSite`는 구분한다.
- `selected_pollutants`: 현재 표시 물질 배열. 잠금 물질도 원래 선택 사실을 보존하며 몰래 NOx/SOx로 필터링해 의미를 바꾸지 않는다.
- `chart_range`: 시작/종료 시각 또는 null. 종료는 시작보다 뒤여야 한다.
- `archive_reference_time`: 전체 보관자료 기준시각. 실제 벽시계/굴뚝별 측정시각과 별개다.
- `data_revision`, `status_policy_version`, `capability_version`, `context_fingerprint`: 요청 당시 자료·설정·선택 검증용 문자열.
- `filters`, `visible_site_ids`: 화면 지역/검색/상태/실제 표시 대상. 전체 보관자료 모집단의 대체값이 아니다.

## QueryIR

- `version`: 이번 내부 형식 `1`.
- `intent`: `latest | list | rank | aggregate | status | view | legal | unknown`.
- `scope`: `selected_stack | facility | region | archive | visible`와 해석된 내부 ID. 범위 없는 목록/순위는 미완성이다.
- `pollutants`: 기존 소스 코드 `NOx | SOx`만 실행 가능. 잠금 코드 `TSP | HCl | CO | NH3 | HF`는 `POLLUTANT_LOCKED`.
- `metric`: `measurement | threshold_ratio | display_status | mean | max` 또는 미확정 null. 순위의 측정값/비율 미정은 확인한다.
- `operator`: `gt | gte | lt | lte | eq | none`. 수치의 초과/이상과 화면 상태 이름을 섞지 않는다.
- `limit`: 순위 요청의 양의 정수 N. 미확정이면 확인하고 반환 수는 조회 가능한 모집단을 넘지 않는다. 요청 수/실제 수를 표시한다.
- `time`: `latest | calendar | archive_recent | chart | explicit`의 기준, 절대 from/to, 실제 received_at, archive_reference_time. 달력은 `[from,to)`, 최근/화면 조회는 기존 그래프와 같은 측정시각 `from<=t<=to`로 구분하여 trace에 남긴다.
- `alignment`: 복수 최신값의 측정시각 불일치가 있으면 확인 필요. 사용자가 각 굴뚝 최신값임을 명시/확인했거나 동일 시각인 경우에만 비교한다. 임의 허용 시간차 없음.
- `provenance`: 필수 조건별 `question | ui | confirmed` 출처.
- `unresolved`, `unparsed_conditions`, `negation`: 미확정 조건과 전체 조건의 파싱 결과. 실행 조건에 영향을 주는 잔여 내용이 있으면 실행 불가.
- `validation`: `PENDING | VALID | NEEDS_CLARIFICATION | UNSUPPORTED | BLOCKED`. 첫 버전에는 LLM 대체 해석 실행 경로 없음.
- `plan`: 허용된 단일 조회/계산 또는 명시적 화면 명령. 일반 복합 DAG는 이번 범위에서 실행하지 않는다.

## ObservationEvidence

- `site_id`, `stack_id`, `stack_code`, `pollutant`, `measured_at`: 정확한 원 관측 식별 및 측정 시점.
- `raw_value`, `numeric_value`, `raw_limit`, `numeric_limit`, `value_kind`: 원문과 숫자 변환을 함께 보존한다. NULL/상태를 0으로 변환하지 않는다.
- `unit`, `unit_source`: `existing_frontend_reference | unconfirmed` 등 원 자료의 확인 수준을 보존한다. 다른 관측의 단위를 몰래 보충해 확정 단위로 표시하지 않는다.
- `threshold_source`: 원 API 응답의 기준 필드라는 근거. 법적 적용성 확인 완료라는 뜻이 아니다.
- `source_ref`, `data_revision`: 기존 원본 object key/행 또는 로컬 파일/관측 식별을 보존한다. 내부 메타에 자격증명을 넣지 않는다.
- `scope_basis`: 불변 전체 최신 스냅샷인지, 특정 사업장·기간 이력인지 표시한다.

## ReferenceStatistics

- `operation`: `mean | max`. 해당 굴뚝·물질·요청 기간에 속한 측정시각의 숫자 관측으로 산술 계산한다. 시간 가중 평균이나 법정 평균이 아니다.
- `value`: 숫자 관측이 0건이면 null. 숫자 0을 누락으로 취급하지 않는다.
- `numeric_count`, `excluded_count`, `excluded_by_reason`: 값/상태/NULL/미존재 등의 포함·제외 내역. 같은 관측을 중복 제외하지 않는다.
- `requested_range`, `observed_first`, `observed_last`, `observed_count`, `partial_coverage`: 요청 기간과 확보된 관측을 구분한다. 팀 기대 슬롯/유효값 계약 없이 공식 결측률을 계산하지 않는다.
- `quality_notes`: 숫자 파싱과 측정 유효성 판정의 차이, 음수/단위 미확인 등 근거 제한을 표시한다.

## DisplayStatusPolicy / Capabilities

- 상태 정책: `version`, `temporary:true`, 순서 있는 `levels`(id·label·경계·비교 연산·기존 색상 토큰), 정상/미판정, 우선 확인 구간과 설명 문구. 경계 중복·순서 역전·비정상 숫자를 거부한다.
- 상태 증거: 대상이 개별 물질/굴뚝 대표/사업장 대표인지와 적용 물질 집합, 비율, 정책 버전. 잠금 물질이 대표 상태를 결정해도 NOx/SOx 원인으로 바꾸지 않는다.
- capability: `version`, 해금/잠금 코드, 허용 의도/화면 명령. 물질 해금 여부는 화면에 적용한 `pollutant-capabilities.js`를 재사용하고 별도 중복 목록을 만들지 않는다. 최초 NOx/SOx만 해금한다. 잠금 해제는 자료/모델 지원 범위 확인 후의 별도 변경이다.
- 수치 부등호와 사용자 경고선(현재 10~100%)은 상태 경계와 독립이다. 원 응답 기준값과 모델 출력을 변경하지 않는다.

## ClarificationSession / QueryResponse

- 확인 세션: request_id·보존 IR·조건 출처·현재 질문·서버 권한이 아닌 로컬 capability 범위·문맥 fingerprint와 허용 옵션 ID를 메모리에 보관한다.
- 새 질문/취소/창 닫기/자료·설정 변경 시 이전 요청의 결과 반영을 중단한다. 확인 도중 UI에서 보충한 값이 바뀌면 재확인한다.
- 응답 `kind`: `answer | clarification | unsupported | blocked | error`.
- `executed`: 확인/차단/지원 불가/오류는 false. 읽기/화면/기존 검색 성공만 true이며 실제 수행한 operation을 남긴다.
- `effective_scope`, `time_basis`, `metric_definitions`, `sources`, `data_quality`, `calculation_trace`, `data_revision`, `status_policy_version`: 결과에 필요한 근거와 제한을 명시한다.
- 법령 결과는 302의 `status/evidence/as_of/limitations`를 그대로 어댑트한다. 미확보 시각·근거 없음은 숫자 답변으로 대체하지 않는다.

## 상태 전이

`입력 → 정규화/파싱 → 문맥 결합 → 검증 → [확인 대기 | 차단 | 미지원 | 실행] → 결과 검증 → 표시`.

확인 대기는 사용자 옵션 응답 뒤 다시 검증으로 돌아간다. 옵션 클릭으로 검증기를 우회하지 않는다. 늦은 비동기 완료는 현재 request_id/fingerprint와 맞지 않으면 표시/화면 변경을 하지 않는다.
