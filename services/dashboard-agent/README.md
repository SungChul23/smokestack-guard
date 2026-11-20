# dashboard-agent

에이전트 서버(LangChain + Bedrock). 지금은 배포 길을 확인하는 최소 앱이고, D·E가 이 폴더에서 이어서 개발한다.

- 실행 환경 약속(포트, `/health`, `/agent/` 접두사, 환경 변수): [contracts/app-runtime.md](../../specs/a-platform/009-service-infra/contracts/app-runtime.md)
- 배포: 이 폴더가 바뀐 커밋이 main에 머지되면 `.github/workflows/dashboard-agent.yml`이 이미지를 만들어 켜진 서버에 배포한다. PR에서는 테스트·빌드만 한다.

## 질문 처리

`POST /agent/chat` 하나로 질문(`message`)과 카드 답(`resume`)을 받는다. 로그인 필수이고 사용자 id는 토큰의 `sub`에서만 얻는다.
계약·결정 근거: [specs/d-analytics/314-front-interpretation-decisions/contracts-draft.md](../../specs/d-analytics/314-front-interpretation-decisions/contracts-draft.md)

```text
질문 → guard(차단·인사·개인정보 가림) → understand(유형·칸 뽑기) → judge(빠진 칸 판정)
        ─ 빠짐 → ask(카드, interrupt) ─ 답 ┐
        └ 충족 → run(유형별 도구) → compose ◀┘
```

질문 유형(`intent`)
- `aggregate`: 특정 굴뚝의 평균·최댓값·최솟값·합계 (굴뚝·물질·기간·집계가 필요)
- `rank`: 전국 굴뚝 순위 (물질 한 가지와 기간이 필요, 집계는 기본 최댓값, 기본 5곳·최대 10곳)
- `freshness`: 데이터가 어느 측정 시각까지인지 ("최신" 대신 시각을 말하고, 오래되면 알림)
- `gap`: 데이터가 비는 이유 (상태별 구간 수와 긴 공백. 원인을 추정하지 않고 API 원문 상태만 옮김)

- 입력 가드레일(`guard.py`): 확실한 공격 패턴(지시 무시, 비밀 요청, 파괴적 명령, 데이터 변조)만 차단하고 짧은 말은 막지 않는다. 개인정보(전화·이메일·주민번호·카드)는 서비스 입구에서 가려서 그래프·체크포인트에 원문이 남지 않는다.
- LangGraph 그래프: `app/agent/graph.py`. 흐름은 코드가 정하고, 해석기(모델)는 칸 값만 뽑는다.
- 카드 문구와 선택지는 코드가 정한다. 모든 카드에 "이 부분은 빼고 진행"이 있고 굴뚝 카드에는 "이 중에 없음"이 있다.
- 집계는 `status_code == 0`(정상 숫자)인 관측만 쓴다. 상태 행(미수신·보수 중 등)의 값 0은 섞이지 않는다.
- 응답의 숫자는 `numbers`로 분리하고, 답변 문장의 숫자와 대조한다(`app/agent/verify.py`).
- 같은 대화에서 "그럼 SOx는?"처럼 이어 묻는 조건은 15분 동안 이어받는다. 값은 매번 다시 읽는다.
- 사업장 인식(`names.py`): 지역 → 사업장 → 굴뚝 순서. 정확 일치 → 정규화(법인 표기·띄어쓰기·영문 읽기) → 글자 검색은 확실할 때만 자동 선택, 아니면 후보 카드(최대 3). 이름 속 숫자는 굴뚝 번호로 읽지 않는다. 형태소 분석기는 쓰지 않는다. 설계·측정: [313 name-resolution.md](../../specs/d-analytics/313-stack-target-resolution/name-resolution.md)
- 시간 표현(정규식): 어제/어저께/오늘/금일, 지난·최근 N시간(한글 숫자 포함), `2026-11-11`·`11월 11일`·`11/11`·`11일`, 지금·현재(지원 안 함 안내).
- 복합 질문(집계·기간·굴뚝이 여럿, 다른 기능 요청, 비교·정정)은 단서로 가려 단일 흐름으로 보내지 않는다. 계획기(LLM)가 없으면 일부만 답하지 않고 멈춰서 알린다. 있으면 부분별로 실행하고 부분마다 상태를 돌려준다. 모호하거나 단정할 수 없는 부분(지역 말, 후보 여럿, 없는 기간·물질)은 AI가 채우지 않고 카드로 묻는다. 설계: [compound-plan.md](../../specs/d-analytics/314-front-interpretation-decisions/compound-plan.md)
- 카드에서 "이 중에 없음"을 고르면 사업장 이름을 다시 받아 직전 조건을 이어서 조회한다(15분). 2번 연속 못 찾으면 지도 선택을 안내한다.
- 같은 `request_id`가 다시 오면 저장된 응답을 돌려주고, 만료되었거나 다른 사용자의 `card_id`는 거절한다.

**아직 연결하지 않은 것(알려진 한계)**
- 해석기: 정규식(`RuleExtractor`)만 쓴다. `BedrockExtractor`는 요청 모양만 시험했고 실제 호출은 하지 않았다. 정규식이 못 채우면 원문을 LLM에 보내는 합성 해석기는 아직 없다(314 D1).
- 데이터: RDS(`ref`·`obs`) 읽기를 구현했다(`AGENT_DATA_SOURCE=rds`, spec 316). **실제 RDS에는 아직 접속하지 못했다**(서버 역할에 `rds-db:connect`가 필요하다). 그 밖에는 시험용 메모리 자료와 로컬 하루치 파일(`AGENT_LOCAL_DAY_DIR`)을 읽는다.
- 대화 상태: 기본은 서버 메모리(`InMemorySaver`)라 서버가 2대면 끊긴다. `AGENT_CHECKPOINT=postgres`로 RDS(`app` 스키마)에 저장하게 구현했고 서버 2대 흉내 시험을 통과했다(spec 319). 실제 RDS에서는 아직 실행하지 못했다. 오래된 대화를 지우는 정리 정책은 없다.
- 굴뚝 해석: 초성 줄임말·같은 이름의 다른 사업부는 못 가린다(카드로 묻거나 LLM 몫). 자세한 한계는 313 name-resolution.md. "지금·현재" 조회는 지원하지 않는다.
- 전국 순위는 요청 때 전체 굴뚝을 훑는다(로컬 하루치 3,480곳에서 약 2.4초). 운영에서는 일일 요약 표(`obs.daily_stack_summary`)를 읽는 구현으로 바꾼다.
- 예측 에이전트는 없다(E의 출력 형식 대기). 근거(법령 조문 검색)·일일 요약은 있다. 설계: [compound-plan.md](../../specs/d-analytics/314-front-interpretation-decisions/compound-plan.md)

## 서버 환경 변수

서버가 뜰 때 SSM `/tms/app/config/<이름>`(예: `agent-data-source`)이 `<이름 대문자, - 는 _>`로 들어간다.

| 환경 변수 | 값 | 설명 |
|---|---|---|
| `AGENT_DATA_SOURCE` | `rds` | 관측을 RDS에서 읽는다. 없으면 `AGENT_LOCAL_DAY_DIR`(하루치 파일) 또는 빈 데이터 |
| `AGENT_CHECKPOINT` | `postgres` | 대화 상태·재시도 응답을 RDS에 저장한다. 서버를 2대 이상 켜기 전에 필요하다. 기본 `memory` |
| `AGENT_LLM_BACKEND` | `none` \| `bedrock` | 아래 "LLM 연결" 참고. 켜기 전까지 `none` |
| `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER` | 엔드포인트, `5432`, `tms`, `tms_app` | RDS 접속(IAM 인증, 비밀번호 없음). 사용자는 읽기 전용 `tms_app` |
| `DB_SSLROOTCERT` | 인증서 묶음 경로 | 있으면 `verify-full`, 없으면 `require` |

DB가 닫혀 있으면 질문은 500이 아니라 **503**과 안내 문구로 끝난다(접속 정보는 응답·로그에 남지 않는다). `/health`는 DB와 무관하게 200이다.

## LLM 연결 (해석기·계획기)

`AGENT_LLM_BACKEND`로 고른다. 같은 코드 경로이고 클라이언트만 바뀐다.
- `none`(기본): 정규식만. 복합 질문은 일부만 답하지 않고 멈춰서 알린다.
- `bedrock`: `AGENT_BEDROCK_MODEL`(모델/추론 프로필 ID), `AWS_REGION`(기본 ap-northeast-2). 강제 도구 호출 `extract`·`plan`, temperature 0.
- `local-agent`(개발용): `AGENT_LOCAL_AGENT_DIR` 아래 `requests/`에 요청 파일을 쓰고, 로컬 에이전트(Claude Code의 Haiku 서브에이전트)가 `responses/`에 답을 쓰면 다음 호출부터 쓴다. 답이 없으면 해석기는 정규식 결과로, 계획기는 "질문을 나누지 못했습니다"로 안전하게 이어진다.

## 로컬

```bash
pip install -e ".[dev]"
ruff check . && pytest -q
uvicorn app.main:app --reload --port 8000
```

<<<<<<< HEAD
로컬 하루치 자료로 돌려 보려면(로그인 검증을 끄고 현재 시각을 고정한다):

```bash
AUTH_DISABLED=1 AGENT_FIXED_NOW=2026-11-11T09:00 \
AGENT_LOCAL_DAY_DIR=<public/data/day 경로> uvicorn app.main:app --port 8000
```

`AUTH_DISABLED`는 운영 서버에 넣지 않는다.
=======
## 로그인·자격 (013)

| 라우트 종류 | 붙이는 것 | 예 |
|---|---|---|
| 공개 | 없음 | `/health` |
| 로그인만 | `user: LoggedInUser` | `/api/me`, `/api/invite` |
| **기본** | `user: CurrentUser` (로그인 + 그룹 `members`) | 그 밖의 모든 라우트 |

자격이 없으면 `403 {"detail": {"code": "not_member", …}}`. 로컬 개발은 `AUTH_DISABLED=1`(로그인·자격 모두 건너뜀, 운영 서버에는 넣지 않음).
약속: `specs/a-platform/013-google-login-invite/contracts/auth-api.md`
>>>>>>> origin/main
