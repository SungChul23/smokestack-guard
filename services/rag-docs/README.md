# rag-docs

에이전트가 법령·고시·업무편람을 근거로 답하도록 하는 RAG 문서 지식 기반의 로컬 도구다. 설계: [specs/a-platform/016-rag-knowledge-base](../../specs/a-platform/016-rag-knowledge-base/spec.md)

```
PC의 PDF 41개 ─ trim_pdf(별표 8) · stage_upload ─▶ 업로드 폴더 laws/·handbook/ (PDF)
   ─ pdf_to_md (쪽마다 Sonnet 4.6, 검사·재시도·캐시) ─▶ md 폴더 laws/·handbook/
   ─ make_metadata --format md · check_metadata · check_chunks --local ─▶ + <파일>.md.metadata.json
   ─ aws s3 sync (md·메타데이터만) ─▶ s3://smokestack-tms-rag-952900391026/
   ─ 동기화(파싱 없음) ─▶ Bedrock 지식 기반 (Titan V2 1024) ─▶ OpenSearch tms-logs / rag-docs
   ─ rag_query (HYBRID · 현행 우선 · 문서 지목 필터 · 이름표 머리말) ─▶ ask.py · run_eval.py · 에이전트(D)
```

| 파일 | 하는 일 |
|---|---|
| `docs_catalog.csv` | 문서 41개의 확인된 메타데이터 원장. 사람이 고치고 PR로 리뷰한다. 빈 칸 = 확인 안 됨. `caveat` = 모델에 함께 넘길 문서별 주의 문구 |
| `missing_fields.csv` | `make_metadata.py`가 쓰는 문서별 빠진 항목(확인 안 된 칸) |
| `catalog.py` | 원장 형식·허용 값·메타데이터 변환 규칙(다른 스크립트가 함께 씀) |
| `trim_pdf.py` | PDF 쪽 범위 자르기(시행규칙 별표 8 → 현행 21~55쪽) |
| `stage_upload.py` | 원장대로 업로드 폴더(`laws/`·`handbook/`)를 구성 |
| `pdf_to_md.py` · `parsing_prompt.md` | 쪽 그림 → Sonnet 4.6 → md. 칸 수·겹친 글자·머리글·모델 메모 검사, 재시도, 쪽별 캐시(`cache/`, 저장소 밖). 지식 기반 안 파서는 표 칸을 빠뜨려 쓰지 않는다(research R4b) |
| `check_chunks.py` · `golden_rows.yaml` | 로컬 md 또는 OpenSearch 조각의 칸 어긋남·머리글·겹친 글자·모델 메모·정답 행 검사 |
| `make_metadata.py` · `check_metadata.py` | 메타데이터 파일 생성·검사 |
| `rag_query.py` | 검색·답변 규칙(에이전트도 같은 규칙, `contracts/agent-connection.md`) |
| `ask.py` · `run_eval.py` · `eval_questions.yaml` · `eval_results/` | 로컬 질문 도구, 시험 질문 15개(쉬움·중간·어려움 각 5)와 채점 결과 |

- **PDF 원본은 저장소·버킷에 넣지 않는다.** A의 PC(`E:\study_DE\rag_docs\base`·`extra`)에만 둔다. 버킷에는 md와 메타데이터만.
- 문서 버킷의 데이터 소스 폴더에는 md와 `.md.metadata.json`만 둔다. 다른 파일은 문서로 색인된다.
- 캐시(`cache/`)의 수동 수정(쪽 JSON의 `fixed_by`)은 저장소에 없다. 시행규칙 별표 8을 `--redo`로 다시 변환하면 표 복원을 다시 해야 한다(research R9a).
- 데이터 소스 laws·handbook은 동시에 동기화할 수 없다(하나 끝난 뒤 다음).
- 실행 순서: [quickstart](../../specs/a-platform/016-rag-knowledge-base/quickstart.md)

## 시험

```bash
uv venv && uv pip install -r requirements.txt
.venv/bin/python -m pytest -q && .venv/bin/ruff check .
```
