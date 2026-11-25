# Quickstart: RAG 문서 지식 기반 (016)

사람이 실행한다(AI는 fmt·validate까지). PowerShell은 Terraform, WSL은 Python·aws CLI.

## 0. 준비

- 원본 PDF: `E:\study_DE\rag_docs\base`(15), `E:\study_DE\rag_docs\extra`(24) — WSL `/mnt/e/study_DE/rag_docs/…`
- 업로드 폴더: `E:\study_DE\rag_docs\upload\{laws,handbook}` (스크립트가 채움)
- 경로는 영문으로 둔다: 터미널 인코딩에 따라 `/mnt/c/Users/<한글 이름>` 경로를 입력할 때 "경로 없음"이 났다(2026-11-23). 저장소 안에는 두지 않는다(PDF 커밋 방지)
- WSL: `cd services/rag-docs && uv venv && uv pip install -r requirements.txt` (boto3, pypdf, pyyaml, pytest)

## 1. 인프라 1단계 (버킷·역할)

```powershell
cd infra\stacks\tms-rag; terraform init; terraform plan; terraform apply
cd ..\tms-log-search; terraform plan   # 접근 정책에 tms-rag-kb 추가만 나와야 함
terraform apply
```

## 2. 인덱스·역할 매핑

```bash
cd services/log-search
python setup_opensearch.py --dry-run   # rag-docs 인덱스 생성, rag_kb_writer 역할·매핑이 보여야 함
python setup_opensearch.py
```

확인: Dev Tools `GET rag-docs/_mapping` → `bedrock-vector` knn_vector 1024, `bedrock-text` analyzer `korean`.

## 3. 문서 준비 (로컬, research R4b)

사용자 터미널은 한글 경로 입력이 깨지므로 영문 폴더를 쓴다(예: `E:\study_DE\rag_docs` = `/mnt/e/study_DE/rag_docs`).

```bash
cd services/rag-docs
R=/mnt/e/study_DE/rag_docs
python trim_pdf.py $R/base/대기환경보전법시행규칙_별표8_배출허용기준_제71호_20261112.pdf \
  --pages 21-55 --out $R/upload/laws/대기환경보전법시행규칙_별표8_배출허용기준_현행_제71호_20261112.pdf
python stage_upload.py --src $R/base $R/extra --dest $R/upload        # 원장대로 laws/·handbook/에 PDF 복사
python pdf_to_md.py --src $R/upload --dest $R/md --dry-run           # 변환할 쪽·예상 비용(Sonnet 4.6, 쪽당 약 2.5센트)
python pdf_to_md.py --src $R/upload --dest $R/md [--doc <doc_id>]     # 걸린 쪽은 원본과 대조해 캐시 쪽 JSON을 고치고 다시 실행(호출 없이 조립)
python make_metadata.py --dest $R/md --format md                     # .md.metadata.json 41개 + missing_fields.csv(저장소)
python check_metadata.py --dest $R/md                                # 41/41
python check_chunks.py --local $R/md                                 # 확인 필요 0개(칸·머리글·겹친 글자·모델 메모·정답 행)
aws s3 sync $R/md s3://smokestack-tms-rag-952900391026/ --exclude "*" --include "*.md" --include "*.md.metadata.json" --dryrun
# 확인 뒤 --dryrun 빼고 실행. 이름표만 다시 만든 경우는 --size-only (내용 같은 파일 재업로드 방지)
```

## 4. 인프라 2단계 (지식 기반)

```powershell
cd infra\stacks\tms-rag; terraform plan; terraform apply      # rag_kb_enabled·agent_retrieve_enabled 기본 true
terraform output knowledge_base_id; terraform output data_source_ids
```

## 5. 동기화

데이터 소스는 하나씩(동시 동기화 불가). 파싱 없이 md를 읽고 임베딩만 한다(1센트 안팎).

```bash
aws bedrock-agent start-ingestion-job --knowledge-base-id <KB> --data-source-id <laws DS>
aws bedrock-agent list-ingestion-jobs --knowledge-base-id <KB> --data-source-id <laws DS> \
  --query 'ingestionJobSummaries[0].{status:status,stats:statistics}'      # COMPLETE 뒤 handbook
aws bedrock-agent start-ingestion-job --knowledge-base-id <KB> --data-source-id <handbook DS>
python check_chunks.py                                                    # 실제 인덱스 검사, 확인 필요 0개
```

## 6. 시험

```bash
export RAG_KB_ID=<KB>
python ask.py "질소산화물 배출허용기준은 어디에 정해져 있나?"   # 1위 시행규칙 별표 8 (시행령 별표 8 아님)
python ask.py "현행 대기 초과배출부과금 산정지수는?" --answer  # 고시 제2025-58호, 6.8876
python run_eval.py --kb $RAG_KB_ID                               # 통과율 ≥ 80%(쉬움·중간·어려움별로도 표시), 같은 번호 별표 100% (SC-003)
```

Dev Tools: `GET rag-docs/_search?size=20` 무작위 조각에 `국가법령정보센터` 머리글이 없는지(SC-005), `GET _nodes/stats/jvm`·CloudWatch `JVMMemoryPressure` 관찰(SC-007).

## 7. 에이전트 연결

`tms-rag` apply(기본값으로 서버 역할 Retrieve 권한 + SSM `/tms/app/config/rag-knowledge-base-id`). 서버 확인은 콘솔 EC2 → `tms-agent` → 연결 → Session Manager에서 `contracts/agent-connection.md` §확인 명령 → 1위 `air-decree_appx-15`.

`contracts/agent-connection.md`를 D에게 공유.

## 되돌리기

- 지식 기반만 내리기: `rag_kb_enabled=false` apply (버킷·인덱스는 남음, 에이전트 권한·SSM도 함께 지워짐)
- 인덱스 다시 만들기: Dev Tools(마스터) `DELETE rag-docs` → `setup_opensearch.py` → 재동기화
