# rag-docs

에이전트가 법령·고시·업무편람을 근거로 답하도록 하는 RAG 문서 지식 기반의 로컬 도구다. 설계: [specs/a-platform/016-rag-knowledge-base](../../specs/a-platform/016-rag-knowledge-base/spec.md)

```
PC의 PDF 39개 ─ trim_pdf(별표 8) · stage_upload ─▶ 업로드 폴더 laws/·handbook/
   ─ make_metadata · check_metadata ─▶ + <파일>.metadata.json ─ aws s3 sync ─▶ s3://smokestack-tms-rag-952900391026/
   ─ 동기화 ─▶ Bedrock 지식 기반 (Claude Haiku 4.5 파서 → Titan V2 1024) ─▶ OpenSearch tms-logs / rag-docs
   ─ ask.py · run_eval.py ─▶ 조각·출처·답변, 시험 질문 통과율
```

| 파일 | 하는 일 |
|---|---|
| `docs_catalog.csv` | 문서 39개의 확인된 메타데이터 원장. 사람이 고치고 PR로 리뷰한다. 빈 칸 = 확인 안 됨 |
| `missing_fields.csv` | `make_metadata.py`가 쓰는 문서별 빠진 항목(확인 안 된 칸). 공공누리 유형·원본 주소는 원장 밖(이번 범위 아님) |
| `catalog.py` | 원장 형식·허용 값·메타데이터 변환 규칙(다른 스크립트가 함께 씀) |
| `parsing_prompt.md` | 지식 기반 파서 지시문(머리글 제거, 표 유지) |
| `trim_pdf.py` | PDF 쪽 범위 자르기(시행규칙 별표 8 → 현행 21~55쪽) |
| `stage_upload.py` | 원장대로 업로드 폴더(`laws/`·`handbook/`)를 구성하고 `aws s3 sync` 명령을 출력 |
| `make_metadata.py` · `check_metadata.py` | 메타데이터 파일 생성·검사 |
| `ask.py` · `run_eval.py` · `eval_questions.yaml` | 로컬 질문 도구, 시험 질문 묶음(쉬움·중간·어려움 각 5) |

- **PDF 원본은 저장소에 넣지 않는다.** A의 PC(`smokestack_rag`, `smokestack_rag_추가`)와 문서 버킷에만 둔다.
- 문서 버킷의 데이터 소스 폴더에는 PDF와 `.metadata.json`만 둔다. 다른 파일은 문서로 색인된다.
- 실행 순서: [quickstart](../../specs/a-platform/016-rag-knowledge-base/quickstart.md)

## 시험

```bash
uv venv && uv pip install -r requirements.txt
.venv/bin/python -m pytest -q && .venv/bin/ruff check .
```
