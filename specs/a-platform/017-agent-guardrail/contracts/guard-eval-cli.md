# Contract: 시험 도구 `guard_eval.py`

```
.venv/bin/python guard_eval.py [--guardrail-id ID] [--version N] [--cases guard_cases.yaml]
                               [--only GROUP[,GROUP]] [--regex-guard PATH] [--enforce LIST]
                               [--out eval_results/] [--json]
```

| 옵션 | 뜻 |
|---|---|
| `--guardrail-id` | 없으면 환경 변수 `GUARDRAIL_ID`, 그다음 SSM `/tms/app/config/guardrail-id` |
| `--version` | 없으면 `GUARDRAIL_VERSION`, 그다음 SSM. `DRAFT`도 허용(콘솔 시험 가드레일용) |
| `--only` | 묶음만 시험 |
| `--regex-guard` | D의 입력 가드 파일 경로. 주면 INPUT 문장을 그 `check_input`에 먼저 넣고 결과를 나란히 적는다. 파일은 저장소 밖 |
| `--enforce` | `text_out` 계산에 쓸 적용 목록(기본: SSM 값, 없으면 `none`). 판정(맞음/오탐/놓침)은 모드와 상관없이 "걸렸는가"로 본다 |
| `--out` | 기록 파일 폴더. 파일 이름 `<YYYY-MM-DD>.md`(같은 날 다시 돌리면 `-2`…) |
| `--json` | 표 대신 JSON 한 줄씩 |

## 판정

| 기대 | 맞음 | 오탐 | 놓침 |
|---|---|---|---|
| `pass` | 아무 정책도 안 걸림 | 하나라도 걸림(개인정보 가림 포함) | — |
| `intervene` | 걸림(감지 포함). `policy`가 있으면 그 정책이 걸림 | — | 안 걸림 또는 다른 정책만 |
| `mask` | `must_mask` 모두 가려짐, `must_keep` 모두 남음 | `must_keep` 중 가려진 것 | `must_mask` 중 남은 것 |

## 출력

화면: 문장 표(id, 묶음, 방향, 기대, 결과, 걸린 정책, 지연 ms, 판정) → 오탐 목록 → 놓침 목록 → 요약. 같은 내용을 기록 파일로 남긴다(data-model §5).

## 종료 코드

| 코드 | 뜻 |
|---|---|
| 0 | 실행 완료(오탐·놓침이 있어도 0 — 기준 맞추기 도구라서) |
| 2 | 인자·설정 오류(ID 없음, 문장 파일 형식 오류, 자격 증명 없음) |
| 3 | 권한 거부 또는 가드레일 없음 |

## 비용

문장 하나당 1회 호출. 60개 문장 시험 1회 몇 센트 이하. 사용 단위 합계를 기록에 적는다.
