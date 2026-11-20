# 접점 초안: 요청·응답 계약, 계획 객체, 도구 등록부

[명세](spec.md) · [오케스트레이션](orchestration.md) · 작성일: 2026-11-18 · 상태: **초안. 같이 고치며 정한다.** 아래는 모두 제안이다.

모든 층이 맞물리려면 먼저 정해야 하는 접점이 세 개 있다. (1) 프런트와 서버 사이의 요청·응답, (2) 오케스트레이터가 에이전트에 일을 시키는 계획 객체, (3) 에이전트가 쓰는 도구의 입출력. 내용이 정해지기 전에 형식부터 고정해 두면 나머지를 따로 만들 수 있다.

## 1. 현재 상태 (코드로 확인한 사실)

| 대상 | 현재 |
|---|---|
| Python 서버 (`D/morph-router-20261117/agent_server.py`) | `POST /api/agent/session`, `/ask {session_id, question}`, `/choose {session_id, option_id}`, `GET /health`. 표준 라이브러리 HTTP 서버 |
| 응답 필드 (`public()`) | `route`, `reason`, `executed`, `delivered`, `slot`, `input`, `preserved`, `tone`, `answer`, `cards`, `used_model`, `model`, `inherited`, `elapsed_ms`, `conditions` |
| 배포되는 서버 (`services/dashboard-agent`) | FastAPI, 경로는 `/agent/*`, 로그인 필수(`user: CurrentUser`, `user["sub"]`), 최소 앱뿐 |
| 307 공통 요청 계약 | **문서 검색 요청 계약**이다(`format`, `extent`, `target`, 부족 슬롯). 대화 전체의 요청·응답 계약이 아니다. 근거 에이전트 입력으로 재사용한다 |

## 2. 요청·응답 계약 (제안)

경로: `/agent/...` (ALB가 접두사를 떼지 않는다). 사용자 id는 클라이언트가 보내지 않고 서버가 토큰의 `sub`로 정한다.

### 요청

```json
POST /agent/chat
{
  "conversation_id": "생략하면 새 대화",
  "message": "어제 3번 굴뚝 NOx 평균 알려줘",
  "resume": null,
  "context": { "selectedStackId": "화면에서 선택한 굴뚝(없으면 null)" }
}
```

- 카드에 답할 때는 `message` 대신 `resume: {"card_id": "...", "option_id": "..."}`를 보낸다. 새 질문이면 떠 있는 카드는 닫는다.
- `context`에는 화면이 아는 것만 싣는다. 권한·허용 굴뚝은 싣지 않는다(굴뚝 조회는 제한 없음). 즐겨찾기는 서버가 `user.sub`로 읽는다.
- 질문 길이는 1~1000자(현재 라우터 규칙과 같다).

### 응답

```json
{
  "request_id": "추적 번호",
  "conversation_id": "...",
  "status": "ANSWERED | NEEDS_INPUT | PARTIAL | REFUSED",
  "parts": [
    {
      "part_id": "p1",
      "agent": "data | evidence | prediction | report | ui",
      "status": "DONE | NEEDS_INPUT | UNAVAILABLE | SKIPPED",
      "label": "현황 | 규정 | ...",
      "answer": "문장(템플릿 또는 모델 서술)",
      "numbers": [ { "name": "mean", "value": 12.3, "unit": "ppm", "n_used": 40, "n_excluded": 8, "period": "...", "as_of": "..." } ],
      "evidence": [ { "source": "법령명", "article": "조문", "effective_date": "시행일", "chunk_id": "..." } ],
      "notice": "이 부분을 못한 이유(있을 때)"
    }
  ],
  "card": {
    "card_id": "...",
    "kind": "STACK_CANDIDATES | STACK_CODE | REGION | TIME | POLLUTANT | SCOPE | CHOOSE_PART | MAP_OR_RETYPE",
    "message": "코드가 정한 고정 문구",
    "options": [ { "id": "...", "label": "...", "skip_part": false } ]
  },
  "trace": { "route": "...", "reason": "...", "model": "...", "elapsed_ms": 0, "trace_id": "LangSmith 추적" }
}
```

원칙
- **부분별 상태**: 복합 질문에서 풀리는 부분은 답하고 못한 부분은 `UNAVAILABLE`과 `notice`로 표시한다(합의한 복합 질문 규칙).
- **카드 문구·선택지는 코드가 정한다.** 모델이 쓴 문구를 내보내지 않는다. 모든 카드에 "이 부분은 빼고 진행"(`skip_part`)과, 굴뚝 카드에는 "이 중에 없음"을 둔다.
- **숫자는 `numbers`로 분리**해 출력 검증(숫자 대조)이 문장이 아니라 구조화 값으로 하게 한다.
- **인용은 `evidence`로 분리**해 인용 검사가 한다. 근거가 없으면 `answer` 없이 `UNAVAILABLE`이다.
- **언제 데이터인지 명시한다.** 응답 최상위에 `data_as_of`(어느 측정 시각까지의 데이터인지, `obs.snapshot_meta`의 `measurement_as_of`)를 싣고, 답변은 "○월 ○일 ○시 ○분 측정분 기준"으로 말한다. "최신", "지금"이라고 쓰지 않는다(공개 API 지연이 약 70분이고 데이터는 30분 단위다). 마지막 수집이 오래됐으면(`last_collected_at`) 그 사실도 알린다.
- **화면 동기화·강제 새로고침·서버 푸시는 하지 않는다**(2026-11-18 사용자 결정). 에이전트는 화면이 아니라 RDS를 도구로 읽고, 새로고침은 사용자가 시각을 보고 필요할 때 한다. 화면의 데이터 버전을 요청에 싣지 않는다.
- 현재 필드와의 대응: `route`·`reason`·`model`·`elapsed_ms` → `trace`, `cards` → `card`, `answer` → `parts[].answer`, `executed`·`delivered` → `parts[].status`, `conditions`·`preserved` → `numbers`·`notice`, `inherited`(후속 질문)는 `trace`에 둔다.

## 2-1. 대화 상태 (제안)

"어제 3번 굴뚝 NOx 평균" 다음에 "그럼 SOx는?"처럼 이어 묻는 흐름을 위한 상태다. **답변을 저장하는 캐시가 아니라, 직전에 확정한 조회 조건을 기억하는 상태**다.

| 항목 | 내용 |
|---|---|
| 저장하는 것 | 직전에 확정·실행한 조건 `{stack, pollutants, time, operation, metric}`, 실행·전달 여부, 전달 시각, 떠 있는 카드(`pending`) |
| 이어받는 방식 | 후속 질문이 바꾸는 칸만 `patch`로 뽑고, 나머지는 상태에서 이어받는다(11/18 칸 뽑기 스키마의 `patch`와 같다) |
| 값은 매번 새로 읽는다 | 조건만 재사용하고 도구를 다시 실행해 RDS에서 새로 읽는다. 이전 답의 숫자를 재사용하지 않는다(데이터 질문 답변 캐시는 하지 않는다) |
| 유효 시간 | 15분(현재 코드 `FOCUS_TTL`). 지나면 이어받지 않고 되묻는다 |
| 끊는 경우 | 다른 주제·미완료 요청이 오면 옛 조회를 이어받지 않는다. 카드가 떠 있을 때 새 질문이 오면 카드를 닫는다. 조건을 바꾸지 않는 말(인사 등)은 최대 3번까지 상태를 유지한다(`MAX_BRIDGED_TURNS`) |
| 저장 위치 | LangGraph 체크포인터를 RDS(PostgreSQL)에 둔다. 서버가 2대여도 어느 서버가 받든 이어진다. 지금 코드는 서버 메모리라 2대에서는 끊긴다 |
| 대화가 길 때 | 전체 대화를 매번 모델에 보내지 않고 구조화된 칸과 최근 몇 턴만 유지한다(비용) |
| 요청 재시도 | `request_id`를 멱등키로 써서 같은 카드 선택이 두 번 도착해도 한 번만 처리한다 |
| 후속 질문 판단 | 시험에서 후속 질문은 규칙 96.2%, LLM 80.8%였다(`research.md`). 후속 여부는 규칙이 확정하고 LLM은 보조로 둔다 |
| 측정하지 않는 물질 | 이어받은 굴뚝이 그 물질을 측정하지 않으면(예: SOx는 굴뚝의 약 1/3만 측정) "측정하지 않습니다"로 답한다. 이유는 상태 코드 8(`not_monitored`) |

## 3. 계획 객체 (제안)

오케스트레이터가 만드는 데이터이고, LangGraph 상태에 저장하며 로그에 남긴다. LLM은 칸을 제안하고 코드가 검증한다.

```json
{
  "plan_id": "...",
  "parts": [
    { "part_id": "p1", "agent": "data", "task": "aggregate",
      "slots": { "stack": {"site_id": "...", "stack_code": "3"}, "pollutants": ["nox"],
                 "time": {"kind": "yesterday"}, "operation": "mean", "metric": "value" },
      "depends_on": [] },
    { "part_id": "p2", "agent": "evidence", "task": "search_law",
      "slots": { "topic": "..." }, "depends_on": ["p1"] }
  ],
  "dropped": [ { "part": "…", "reason": "NO_ASSET | NOT_ALLOWED_COMBO | USER_SKIPPED" } ],
  "validation": { "combo": "OK | ASK_ORDER", "missing_slots": [ ] }
}
```

- `agent`는 자산 등록부에 있는 값만 허용한다(`data`, `evidence`, `prediction`, `report`, `ui`).
- 허용 조합만 실행한다: 데이터+근거, 예측+근거, 데이터+화면. 그 밖은 "어느 것부터?"(`CHOOSE_PART`) 카드.
- `slots`는 에이전트별 입력 형식이다. 데이터 에이전트의 칸(`stack`, `pollutants`, `time`, `operation`, `metric`)은 11/18 칸 뽑기 시험의 도구 스키마와 같다(`D/morph-router-20261117/redteam/bedrock_retest.py`의 `SLOTS_TOOL`). 빠진 칸은 코드가 계산한다(`slot_common.expected`).
- `depends_on`으로 순서를 정하고, 앞 단계의 구조화된 사실만 뒤 단계에 넘긴다(문장은 넘기지 않는다).
- 불가능한 부분은 사용자에게 묻지 않고 `dropped`에 남겨 한 줄로 알린다.

## 4. 도구 등록부 뼈대 (제안, 읽기 전용)

모든 도구는 입력이 enum·번호·날짜로만 이루어지고(SQL 문자열 없음), 결과에 `n_used`, `n_excluded`, `period`, `as_of`, `source_version`을 붙인다. 테이블은 [서비스용 테이블 제안](../../../docs/D_SERVICE_TABLES_PROPOSAL_20261118_KO.md) 기준이다.

| 도구 | 입력 | 읽는 곳 | 비고 |
|---|---|---|---|
| `resolve_stack` | 질문의 굴뚝 말, 선택 굴뚝, 지역 답 | `ref.site`, `ref.stack`, `ref.site_name_map` | [313](../313-stack-target-resolution/spec.md) 결과(AUTO/CARD/NONE) |
| `read_values` | `stack_key`, 물질, 시작·종료 | `obs.measurement_30m` | 상태 행은 `status_code`로 구분해 반환 |
| `aggregate_values` | `stack_key`, 물질, 기간, 연산(mean/max/min/sum) | `obs.daily_stack_summary` 또는 `obs.measurement_30m` | `status_code = 0`인 행만 계산 |
| `rank_stacks` | 물질, 날짜, 지표, 개수, 지역(선택) | `obs.daily_stack_summary` | 전국·지역 순위 |
| `national_summary` | 물질, 날짜 | `obs.daily_national_summary` | 최고·평균·보고 굴뚝 수 |
| `explain_gap` | `stack_key`, 물질, 기간 | `obs.measurement_30m`, `ref.status_code` | 결측 이유(상태별 건수, 설명 문구) |
| `data_freshness` | (없음) | `obs.snapshot_meta` | "데이터가 최신인가요?" |
| `search_law` | 질문, 컬렉션, 필터, k | `rag.doc_chunk` | 307 문서 요청 계약을 입력으로 재사용 |
| `get_prediction` | `stack_key` | E 테이블 | 형식은 E가 정한다 |
| `ui_navigate` | 대상 종류, id | (화면) | 에이전트가 아니라 도구 |

## 5. 열린 결정

| # | 결정 | 권장 |
|---|---|---|
| K1 | 요청을 `/agent/chat` 하나로 합칠지, 지금처럼 질문과 선택 두 개로 둘지 | **결정: 하나로 합친다(A안, 2026-11-18 사용자).** 본문은 `message`와 `resume` 중 정확히 하나만 허용(둘 다 있거나 없으면 400). `/session`은 없애고 `conversation_id`를 비우면 새 대화를 만든다. `trace.turn_type`(`MESSAGE`/`RESUME`)을 기록해 로그·LangSmith에서 구분한다. 만료된 `card_id`는 "만료"로 거절하고, `request_id`로 같은 요청의 중복 처리를 막는다. 채팅 주소는 두 종류로 고정하고 취소·피드백·이력 조회는 별도 주소로 둔다 |
| K2 | 스트리밍 응답(`InvokeModelWithResponseStream`)을 쓸지 | 처음엔 안 씀. 부분별 상태가 먼저 필요 |
| K3 | 대화 이력 저장 위치 | RDS(`app.message`), 체크포인트는 LangGraph 체크포인터 |
| K4 | `numbers`·`evidence` 형식을 이 초안대로 고정할지 | 고정(출력 검증이 이것을 읽음) |
| K5 | 기존 필드(`route`, `reason` 등)를 `trace`로 옮기는 호환 기간 | 로컬 프런트가 새 응답을 받을 때 한 번에 |
| K6 | 307을 근거 에이전트의 입력 계약으로만 남기고 이름을 바꿀지 | 이름은 두고 README에서 관계만 적음 |
| K7 | 대화 목록·이력 조회 주소(`GET /agent/conversations`, `GET /agent/conversations/{id}`) | 읽기 전용으로 별도. 로그인 `sub`가 소유한 대화만 반환 |
| D1 | 질문 해석에 형태소 분석기(Kiwi)를 쓸지 | **결정: 쓰지 않는다(2026-11-18 사용자).** 고유 이름(사업장명)을 쪼개지 못하는 순간 부적합이다. 해석은 정규식(확실한 것만) + 사업장 인식기(`names.py`)이고, 정규식이 못 채운 칸이 있거나 신호가 충돌하면 **원문 전체**를 LLM 해석기에 보낸다(정규식 결과는 넘기지 않는다: 틀린 힌트에 끌려가지 않게 하고 두 해석을 독립으로 둔다). LLM이 낸 칸도 코드가 다시 검증한다. 정규식과 LLM이 다르면 자동으로 고르지 않고 카드로 묻는다. 사업장 선택은 LLM이 아니라 인식기가 한다. 근거는 [313 사업장 인식](../313-stack-target-resolution/name-resolution.md) |
| K8 | 카드에서 "이 중에 없음"을 고른 뒤 | **결정: 채팅창을 연 채 사업장 이름을 다시 받는다(2026-11-18 사용자).** 직전 조건(물질·집계·기간)은 유지하고 사업장만 채운다. 물질·집계·기간이 들어 있는 입력은 새 질문으로 처리한다. 15분 안에만 유효하다. "없음" 포함 2번 연속 못 찾으면 "지도에서 굴뚝을 선택한 뒤 다시 질문해 주세요"로 안내하고 대기를 끝낸다(`selectedStackId`로 이미 받을 수 있다) |

이 초안이 정해지면 [tasks.md](tasks.md)의 T040~T043(분류·칸 뽑기 스키마, 판정, 검증기, 카드)과 T060~T061(요청 계약에 선택 굴뚝 추가)을 이 계약 기준으로 갱신한다. 이 계약은 아직 서버에 구현하지 않았다.
