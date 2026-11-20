# Contract: 서버 로그 형식 (API·에이전트 → CloudWatch → OpenSearch)

D가 에이전트·API 라우트를 만들 때 지키는 약속이다. 형식이 맞으면 로그 대시보드에 자동으로 잡힌다.

## 1. 한 줄 = JSON 하나

서버는 표준 출력(stdout)에 **JSON 한 줄**씩 쓴다. JSON이 아닌 줄도 받지만(본문 문자열로 저장) 필드로 거를 수 없다.

공통 키:

| 키 | 필수 | 값 |
|---|---|---|
| `log_type` | 예 | `request` · `activity` · `app` |
| `level` | 아니요 | `ERROR` · `WARNING` · `INFO` · `DEBUG` (없으면 `INFO`) |

## 2. 요청 기록 (`request`) — 미들웨어가 자동으로

```json
{"log_type": "request", "method": "GET", "path": "/api/me", "status": 200, "duration_ms": 12.4, "sub": "1a2b…"}
```
- 상태 확인(`/health`, `/api/health`, `/agent/health`)은 남기지 않는다.
- `status`가 500 이상이면 `level: "ERROR"`, 400대는 `WARNING`.
- `path`는 라우트 원형을 쓴다(쿼리 문자열 제외). 경로에 개인 정보를 넣지 않는다.

## 3. 사용자 활동 (`activity`) — `log_activity(event, sub)`로

```json
{"log_type": "activity", "event": "agent_question", "sub": "1a2b…"}
```

| `event` | 남기는 곳 | 누가 |
|---|---|---|
| `session` | `GET /api/me` (화면 진입) | A (013 라우트) |
| `invite_ok` | `POST /api/invite` 통과 | A |
| `agent_question` | 에이전트 질문 라우트 | **D** |

- **남기지 않는 것**: 이메일, 이름, 초대 코드 입력값, 질문 원문, 답변 원문.
- 새 `event`를 더할 때는 이 표에 한 줄 추가한다.

## 4. 그 밖의 앱 로그 (`app`)

```json
{"log_type": "app", "level": "ERROR", "msg": "RDS 연결 실패", "error": "OperationalError"}
```
- 예외는 종류(`error`)와 짧은 설명만. 비밀값·DB 비밀번호·토큰·요청 본문은 남기지 않는다.
