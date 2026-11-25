# Research: 에이전트 가드레일 2차 검사

2026-11-25. 근거: AWS provider 6.73.0 스키마(`terraform providers schema`로 확인), Bedrock Guardrails 문서, D의 입력 가드(`check_input`, #66 브랜치, 사용자가 대화에 붙여 줌).

## R1. 가드레일 하나에 입력·출력을 함께 둔다

- **Decision**: 가드레일 `tms-agent` 1개. 정책마다 입력 강도·출력 강도를 따로 둔다(`filters_config.input_strength`/`output_strength`).
- **Rationale**: Bedrock 가드레일은 정책별로 입력·출력 기준을 따로 가진다. `ApplyGuardrail`은 `source=INPUT|OUTPUT`으로 어느 쪽 기준을 쓸지 고른다. 가드레일을 둘로 나누면 ID·버전·권한·시험이 두 배가 된다.
- **Alternatives**: 입력용·출력용 2개 — 정책 성격이 크게 다를 때만 의미가 있다(근거 확인은 근거를 넘긴 호출에서만 동작하므로 함께 둬도 된다).

## R2. 등급(tier)은 Standard, 교차 리전 프로필 필요

- **Decision**: `content_policy_config.tier_config.tier_name = "STANDARD"`, `topic_policy_config.tier_config.tier_name = "STANDARD"`, `cross_region_config.guardrail_profile_identifier` = APAC 프로필(변수, 기본 `apac.guardrail.v1:0` — apply 전 콘솔 "교차 리전" 화면에서 정확한 값 확인). 프로필을 쓸 수 없으면 변수로 `CLASSIC`으로 되돌린다.
- **Rationale**: Classic 등급의 유해 내용·거부 주제 탐지는 영어 중심(영어·프랑스어·스페인어)이다. 질문이 한국어라 Standard 등급이 사실상 필요하고, Standard는 교차 리전 처리(가드레일 프로필)를 요구한다. 검사 문장이 서울 밖 APAC 리전에서 처리될 수 있다 — 공개 법령·측정값 질문이고 입력 개인정보는 D가 먼저 가리므로 받아들인다.
- **Alternatives**: Classic — 한국어 바꿔 말하기를 놓칠 가능성이 커서 2차 검사의 의미가 줄어든다. 시험(SC-002)에서 Classic과 비교해 볼 수 있다.

## R3. 감지만/차단은 호출하는 쪽 모드로 정한다

- **Decision**: 가드레일 정책의 동작은 차단(BLOCK)·가림(ANONYMIZE)으로 두고, 에이전트가 SSM `/tms/app/config/guardrail-enforce`(쉼표 목록: `content`, `prompt_attack`, `topics`, `grounding`; 빈 값 = 모두 감지만)를 읽어 **적용할지**를 정한다. 개인정보 가림은 모드와 상관없이 항상 적용한다.
- **Rationale**:
  - provider 6.73의 `aws_bedrock_guardrail`은 유해 내용·개인정보·단어에는 `input_action`/`output_action`(NONE = 감지만)이 있지만, **거부 주제(`topics_config`)와 근거 확인(`contextual_grounding_policy_config`)에는 없다.** 정책 쪽에서 감지만을 일관되게 둘 수 없다.
  - `ApplyGuardrail` 응답에는 정책별 평가(`assessments`: 걸린 주제·필터·점수·동작)가 들어 있어, 호출하는 쪽이 "걸렸지만 이번엔 막지 않음"을 고를 수 있다.
  - 모드를 SSM에 두면 차단으로 바꿀 때 가드레일 새 버전 없이 값만 바꾸면 된다(정책별로 하나씩).
- **감지 모드에서 출력 처리**: 가드레일이 개입하면 `outputs`는 차단 문구가 되어 가린 문장을 잃는다. 그래서:
  - 걸린 것이 개인정보 가림뿐 → `outputs`(가린 문장)를 쓴다.
  - 차단 정책이 걸렸고 그 정책이 감지 모드 → **원문을 쓰되** 개인정보는 응답의 `piiEntities`/`regexes` 일치 문자열로 직접 가린다(`guard_result.py`의 규칙, 에이전트도 같은 규칙).
  - 차단 정책이 걸렸고 그 정책이 적용 모드 → 차단 문구.
- **Alternatives**: 정책마다 `NONE` — 주제·근거 확인이 provider에서 안 됨. 가드레일 2벌(감지용·차단용) — 버전·권한이 두 배.

## R3a. 주제별 적용, `tamper_request`는 감지 신호로만 (2026-11-25 시험 뒤)

- **Decision**: 적용 목록에 주제 이름(`internal_info`, `tamper_request`)을 따로 쓸 수 있게 한다(`topics` = 주제 전부). `tamper_request`는 차단으로 바꾸지 않고 감지 신호(Dashboards)로만 쓴다. 정의는 v1 문구로 되돌린다.
- **Rationale**: v1(오탐 2·놓침 5)→v2(정의를 "실제와 다르게 만들라는 지시"로, 오탐 3·놓침 8). 예시에 없는 새 문장은 요청 1/5만 잡고 질문 1/3을 오탐했다. 바꾸지 않은 `internal_info`도 한 문장 판정이 달라졌다 — 거부 주제 분류기는 한국어에서 같은 대상의 "해 달라"(요청)와 "하면 어떻게 되나"(질문)를 안정적으로 가르지 못한다(`eval_results/2026-11-25.md`, `-2.md`). 대신 막지 않아도 되는 이유가 있다: 에이전트에 측정값을 고치는 쓰기 도구가 없고(구조), 확실한 표현은 1차 정규식이 막고, 보고서 허위 숫자는 출력 근거 확인이 잡는다(4/4).
- **Alternatives**: 정의를 더 다듬기 — 경계만 옮겨 다님. 모델(Haiku)로 의도 분류 — 질문마다 모델 호출 비용·지연, 범위 밖.

## R4. 정책 처음 값

| 정책 | 값 | 이유 |
|---|---|---|
| 유해 내용 HATE·INSULTS·SEXUAL | 입력·출력 HIGH | 도메인에서 정상 질문이 걸릴 일이 적다 |
| VIOLENCE | MEDIUM/MEDIUM | "폭발", "사고" 같은 낱말 |
| MISCONDUCT | **LOW/LOW** | "조작 적발 시 과태료", 법령 답의 "조업정지·고발"이 걸릴 위험이 가장 크다. 조작 요청은 거부 주제가 맡는다 |
| PROMPT_ATTACK | 입력 HIGH, 출력 NONE | 출력에는 의미 없음(서비스 제약) |
| 이미지 | 끔(`input_modalities`/`output_modalities` = TEXT) | 텍스트만 |
| 거부 주제 | 2개(조작 요청 / 내부 정보), 정의에 "묻는 질문은 해당 안 함" | D의 TAMPERING·FALSIFY·CONFIG_TAMPERING / SECRET_REQUEST·INTERNAL_INFO에 대응 |
| 개인정보(관리형) | EMAIL·PHONE ANONYMIZE, `input_enabled=false` | 입력은 D가 가림 |
| 개인정보(정규식) | 주민번호 `\d{6}[-\s]?[1-4]\d{6}`, 한국 전화 `0\d{1,2}[-\s]?\d{3,4}[-\s]?\d{4}` ANONYMIZE, 출력만 | 관리형 PHONE은 한국 번호 형식을 놓칠 수 있다(시험으로 확인). 패턴은 D의 `_PII`와 같게 |
| 근거 확인 | GROUNDING 0.5, RELEVANCE 0.5 | 근거를 넘긴 출력 검사에서만 동작. 시작값 |
| 단어 필터·자동 추론 | 안 씀 | 관리형 욕설 목록은 영어 중심 / 범위에 비해 과함 |

D의 `DESTRUCTIVE`(SQL·셸 문자열)는 가드레일로 옮기지 않는다. 에이전트가 쓰기 SQL·셸 도구를 갖지 않는 구조로 막는다(#66). `SMALLTALK`·`TOO_LONG`은 분기·안내라 코드에 남는다.

## R5. 권한 (최소)

| 주체 | 권한 | 범위 |
|---|---|---|
| 서버 역할 `tms-app-server`(인라인 정책 `tms-agent-guard`) | `bedrock:ApplyGuardrail` | 가드레일 `tms-agent` ARN + 교차 리전 가드레일 프로필 ARN(`arn:aws:bedrock:*:952900391026:guardrail-profile/<프로필>`) |
| 같은 서버 역할 | SSM 읽기 | 이미 `/tms/app/*` 권한 있음(추가 없음) |
| 시험 도구(A의 PC) | A의 IAM 사용자 | 추가 없음 |

가드레일 생성·수정(`CreateGuardrail` 등)은 서버에 주지 않는다. `InvokeModel`/`Converse`에 가드레일을 붙이지 않으므로 그 권한 조건도 필요 없다. 교차 리전 프로필 ARN 형식은 apply 뒤 서버 시험(SC-005)으로 확인한다.

## R6. 비용

- 상시 비용 없음. 검사한 글자 수(텍스트 단위 = 1,000자)와 정책 종류별 단가로 과금. 글자 수 기반이라 질문 1,000자 이하·답 수천 자면 질문당 몇 단위다.
- 유해 내용·거부 주제가 단위당 가장 비싸고 개인정보·근거 확인은 그보다 싸며 정규식은 무료(2026-11 기준 가격 페이지 확인 필요). 질문당 입력+출력 약 0.1~0.3센트로 추정, 근거 확인에 조각(최대 수만 자)을 넘기면 조금 더.
- 시험 도구는 응답의 사용량(`usage`: 정책별 단위 수)을 모아 기록에 적는다 → 추정이 아닌 실측으로 SC-004를 확인한다.

## R7. 버전 관리

- **Decision**: `aws_bedrock_guardrail_version`에 `lifecycle { replace_triggered_by = [aws_bedrock_guardrail.agent] }`, `skip_destroy = true`. SSM `guardrail-version`은 그 버전 번호.
- **Rationale**: 정책을 고치면 새 버전이 생기고 서버는 SSM 값으로 새 버전을 쓴다. 이전 버전은 지우지 않아 되돌릴 수 있다. `DRAFT`는 쓰지 않는다(고치는 즉시 서버에 반영돼 시험 없이 바뀜).

## R8. 호출 실패 시

- 입력 검사 실패(권한·네트워크·지연 초과 3초): D 정규식을 이미 통과했으므로 **계속 진행**하고 실패를 로그에 남긴다.
- 출력 검사 실패: 읽기 답변은 D의 `mask_pii`로 가린 뒤 내보내고 실패를 로그에 남긴다. **보고서 저장·알림 발송은 보내지 않는다**(사람에게 나가는 쓰기는 검사 없이 내보내지 않음).
- 근거: 2차는 보강층이라 1차가 통과시킨 질문을 가드레일 장애로 모두 막으면 서비스가 멈춘다. 쓰기만 보수적으로.

## R9. 시험 문장

- 묶음: `normal`(정상 질문), `risky_word`(위험 낱말이 든 정상 질문 — D 주석 예문 "지워진 건가요", "조작 적발 시 과태료", "변조 방지", "삭제 기준", "덮어쓰기 되는 주기"), `tamper`(조작 요청), `report_alert`(보고서·알림 조작), `internal`(내부 정보), `injection`(프롬프트 공격, 영어·중국어·띄어쓰기 우회 포함), `pii_out`(출력 개인정보, 가짜 값), `number_out`(측정값·날짜가 든 출력 — 가려지면 안 됨), `grounded_out`(근거 + 근거 안/밖 답).
- 방향: 입력 묶음은 D가 가린 형태로 적는다(`[전화번호]` 표시 포함 문장도 하나).
- 개인정보 값은 가짜(`010-0000-0000`, `user@example.com`, 형식만 맞는 주민번호)만 쓴다.

## R10. 가드 기록은 기존 활동 인덱스로, 개인정보는 라우터에서 한 번 더 가림

- **Decision**: 새 전달 경로·인덱스를 만들지 않는다. 에이전트가 `log_type = "activity"`, `event = "agent_guard"` 한 줄을 쓰면 014 라우터가 `activity-*`(28일)로 보낸다. 라우터(`services/log-search/router.py`)는 활동 문서의 `json.question`과 `message`에서 주민번호·카드·전화·이메일을 D와 같은 패턴으로 가린 뒤 보낸다. 활동 인덱스 틀에 `json.question`(text + keyword 256)과 `json.ms`(float)를 명시한다(나머지 새 필드는 기존 동적 규칙대로 keyword).
- **Rationale**: 활동 기록은 이미 회원 id·사건 종류를 모으고 Dashboards 권한(팀원 읽기)도 있다. 개인정보 가림을 에이전트(D)에만 맡기면 코드가 바뀔 때 새어 나갈 수 있어, 저장 직전 A가 관리하는 단계에서 한 번 더 가린다. 라우터는 원본 한 줄을 `message`에도 넣으므로 둘 다 가려야 한다.
- **주의**: 틀 변경은 새로 만들어지는 날짜 인덱스부터 적용된다(오늘 인덱스는 다음 날부터). `json.question`이 동적 규칙으로 keyword가 된 인덱스에서는 낱말 검색이 안 된다 → 적용 다음 날부터 확인. 질문 문장은 nori 없이 기본 분석기(한국어는 어절 단위 검색)로 둔다 — 활동 인덱스에 nori를 쓰려면 016의 nori 패키지 연결(#84) 뒤로 미룬다.
- **Alternatives**: 가드 전용 인덱스 — 보관·권한·틀을 또 만들어야 한다. 에이전트만 가림 — 위 이유로 부족.

## R11. 014 규칙 변경

014 FR-021 "질문 원문을 남기지 않는다"를 "가드에 걸린 질문만, 가린 앞 300자를 28일"로 바꾼다. 걸리지 않은 질문은 여전히 남기지 않는다. 팀원 누구나 Dashboards에서 읽으므로 팀에 알린다(T 목록 📨).
