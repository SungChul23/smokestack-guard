# 에이전트 가드 연결: 018에서 바뀌는 것 (D에게)

기본 연결 방법은 017 [agent-guard-connection.md](../../017-agent-guardrail/contracts/agent-guard-connection.md) 그대로다. 아래만 바뀐다.

## 1. `guard_result.py`를 새 파일로 바꾼다 (필수)

- 저장소 `services/agent-guard/guard_result.py`를 다시 그대로 복사한다.
- 바뀐 점: 가드레일의 **단어 정책** 결과(`wordPolicy`)를 읽는다. 옛 파일은 이 결과를 읽지 않아, 단어에 걸려도 "걸린 것 없음"으로 보고 통과시킨다.
- 함수 이름·인자·`Result` 필드는 그대로다. 호출 코드는 바꿀 필요가 없다.

## 2. 차단 결과를 반드시 쓴다 (확인 요청)

```python
res = guard_result.check(br, cfg, "INPUT", masked_question)
if res.blocked:
    return res.text_out          # 차단 문구. 모델·도구를 부르지 않는다
question_for_model = res.text_out  # 통과면 (가림이 반영된) 문장
```

- 출력도 같다: `res.blocked`면 답변 대신 `res.text_out`(출력 차단 문구)을 보여 준다.
- `res.blocked`를 보지 않고 원래 문장을 넘기면 적용 목록과 관계없이 계속 통과한다.

## 3. 적용 목록 값

- SSM `/tms/app/config/guardrail-enforce`에 `words`가 새로 생긴다.
- A가 시험을 마친 뒤 `content,prompt_attack,internal_info,words`로 바꾼다. 에이전트는 다음 설정 읽기(최대 5분) 때 반영한다. 코드 변경은 없다.

## 4. 기록

- 가드 기록의 `reason`에 `CUSTOM_WORDS`(한국어 단어 목록) 또는 `PROFANITY`(영어 관리형 목록)가 나올 수 있다. 걸린 단어 자체는 기록하지 않는다.

## 5. 확인 순서 (D)

1. 새 `guard_result.py` 복사
2. 로컬에서 "시발 측정값 알려줘" → A가 차단을 켠 뒤에는 차단 문구가 나와야 함(켜기 전에는 통과 + `reason=CUSTOM_WORDS` 감지 기록)
3. "측정 시발점이 언제야?" → 통과
