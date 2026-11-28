# Quickstart: 가드레일 차단 켜기 + 비속어 단어

순서: 해석 규칙 시험(로컬) → ① 단어 목록 apply(감지만) → ② 실제 가드레일 시험 → ③ 적용 목록 apply(차단) → D 확인.

## 0. 해석 규칙 시험 (WSL)

```bash
cd services/agent-guard
.venv/bin/python -m pytest -q        # 단어 정책 가짜 응답 시험 포함
```

## 1. 단어 목록 붙이기 (PowerShell, 감지만)

```powershell
cd infra\stacks\tms-agent-guard
terraform plan     # 가드레일 in-place(word_policy_config), 버전 교체(3 → 4), SSM guardrail-version 3 → 4
terraform apply    # guardrail_enforce는 아직 none
```

①단계에서는 `variables.tf`의 `guardrail_enforce` 기본값을 바꾸지 않는다(커밋 순서: 단어 목록 커밋 → apply → 시험 → 기본값 커밋 → apply).

## 2. 실제 가드레일로 시험 (WSL)

```bash
.venv/bin/python guard_eval.py --enforce content,prompt_attack,internal_info,words
.venv/bin/python guard_eval.py --only profanity,profanity_attached,profanity_like_normal --enforce content,prompt_attack,internal_info,words
```

기대(spec SC-001~004):
- 통과해야 할 문장(017 정상 + `profanity_like_normal`) 오탐 0
- `profanity` 90% 이상 차단, 공격·내부 정보 전부 차단
- `profanity_attached`는 결과만 기록 → 조건부 후보(시발·병신) 결정(research R4)
- 평균 지연 1초 미만

목록을 고치면 1로 돌아간다(새 버전). 결과는 `eval_results/<날짜>.md`에 이유와 함께 남긴다.

## 3. 차단 켜기 (PowerShell)

`variables.tf` 기본값을 `content,prompt_attack,internal_info,words`로 바꿔 커밋한 뒤:

```powershell
terraform plan     # SSM guardrail-enforce 하나만 변경
terraform apply
```

되돌리기: `terraform apply -var 'guardrail_enforce=none'` (가드레일 버전 그대로).

## 4. 확인

- D에게 [contracts/agent-guard-connection-delta.md](contracts/agent-guard-connection-delta.md) 전달 → 새 `guard_result.py` 복사, 로컬에서 비속어 질문이 차단 문구로 나오는지
- Dashboards "에이전트 가드": 차단 기록이 `BLOCKED`, 사유 `CUSTOM_WORDS`로 보이는지
