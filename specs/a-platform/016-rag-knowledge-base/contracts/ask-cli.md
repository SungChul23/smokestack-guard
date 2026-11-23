# Contract: 로컬 질문 도구 `services/rag-docs/ask.py`

A의 PC(WSL)에서 사용자 AWS 프로필로 실행한다. 지식 기반 ID는 코드에 넣지 않고 `--kb` 또는 환경 변수 `RAG_KB_ID`(값은 `terraform -chdir=infra/stacks/tms-rag output -raw knowledge_base_id`).

## 사용

```bash
python ask.py "현행 질소산화물 배출허용기준은?"              # 조각만 (Retrieve)
python ask.py "…" --top 8                                  # 조각 수 (기본 5, 최대 20)
python ask.py "…" --status 현행                             # effective_status 거르기 (여러 번 가능)
python ask.py "…" --answer                                 # 답변 + 인용 (RetrieveAndGenerate)
python ask.py "…" --json                                   # 원자료 JSON
```

- 검색 방식: 혼합(HYBRID). 기본 거르기 없음(시험이 구판도 보게).
- 답변 모델: `--model` 또는 `RAG_ANSWER_MODEL`(기본 Claude Sonnet 4.5 추론 프로필 ARN).

## 출력 (조각)

```
질문: 현행 질소산화물 배출허용기준은?  (조각 5개, 2.1초)

#1  점수 0.734  대기환경보전법 시행규칙 · 별표8 · 2026-11-12 · 현행
    파일 laws/대기환경보전법시행규칙_별표8_배출허용기준_현행_제71호_20261112.pdf  쪽 3
    | 배출시설 | 질소산화물(ppm) | … (본문 앞 200자)
#2  …
```

## 출력 (답변)

```
답변:
…본문…

근거:
[1] 대기환경보전법 시행규칙 별표 8 (2026-11-12 시행, 현행) — 쪽 3
[2] …
```

## 오류

| 상황 | 메시지 | 종료 코드 |
|---|---|---|
| ID 없음 | `지식 기반 ID가 없습니다: --kb 또는 RAG_KB_ID` | 2 |
| 자격 증명 없음·만료 | `AWS 자격 증명을 찾을 수 없습니다 (프로필·리전 ap-northeast-2 확인)` | 2 |
| 권한 없음 | `권한 없음: <API> (<오류 코드>)` | 3 |
| 지식 기반 없음 | `지식 기반 <ID>를 찾을 수 없습니다 (리전·apply 확인)` | 3 |

## 시험 묶음 `run_eval.py`

```bash
python run_eval.py --kb $RAG_KB_ID            # eval_questions.yaml 전체
python run_eval.py --kb … --only q03 q07
```

출력: 질문별 `통과/실패`, 기대 문서 순위, 1위 문서, 전체 통과율, 같은 번호 별표 질문 통과율. 결과 표를 `eval_results/<YYYY-MM-DD>.md`로 저장.
