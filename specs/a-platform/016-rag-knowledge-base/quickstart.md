# Quickstart: RAG 문서 지식 기반 (016)

사람이 실행한다(AI는 fmt·validate까지). PowerShell은 Terraform, WSL은 Python·aws CLI.

## 0. 준비

- 원본 PDF: `C:\Users\성철\Desktop\smokestack_rag`(15), `C:\Users\성철\Desktop\smokestack_rag_추가`(24)
- 업로드 폴더(새로 만듦): `C:\Users\성철\Desktop\smokestack_rag_upload\{laws,handbook}`
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

## 3. 문서 준비 (로컬)

```bash
cd services/rag-docs
python trim_pdf.py "/mnt/c/Users/성철/Desktop/smokestack_rag/대기환경보전법시행규칙_별표8_배출허용기준_제71호_20261112.pdf" \
  --pages 21-55 --out <업로드 폴더>/laws/대기환경보전법시행규칙_별표8_배출허용기준_현행_제71호_20261112.pdf
python stage_upload.py --src <원본 두 폴더> --dest <업로드 폴더>      # 원장대로 laws/·handbook/에 복사 (별표 8 원본 제외)
python make_metadata.py --dest <업로드 폴더>                          # .metadata.json 39개 + missing_fields.csv(저장소)
python check_metadata.py --dest <업로드 폴더>                         # 39/39 통과
aws s3 sync <업로드 폴더> s3://smokestack-tms-rag-952900391026/ --exclude "*" --include "*.pdf" --include "*.metadata.json" --delete --dryrun
# 확인 뒤 --dryrun 빼고 실행
```

## 4. 인프라 2단계 (지식 기반)

```powershell
cd infra\stacks\tms-rag; terraform plan -var rag_kb_enabled=true; terraform apply -var rag_kb_enabled=true
terraform output knowledge_base_id
```

## 5. 동기화

먼저 어려운 문서 3개(시행규칙 별표 36, 별표 8 현행, 관제센터 별표 1)만 업로드 폴더에 두고 laws 동기화 → Dev Tools `GET rag-docs/_search?q=*&size=10`으로 표가 마크다운 표로, 머리글 없이 옮겨졌는지 확인(비용 몇 센트). 괜찮으면 나머지를 sync하고 다시 동기화(바뀐 파일만 처리).


```bash
aws bedrock-agent start-ingestion-job --knowledge-base-id <KB> --data-source-id <laws DS>
aws bedrock-agent start-ingestion-job --knowledge-base-id <KB> --data-source-id <handbook DS>
aws bedrock-agent get-ingestion-job …   # statistics: scanned 38/1, indexed 38/1, failed 0 (SC-001)
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

```powershell
terraform apply -var rag_kb_enabled=true -var agent_retrieve_enabled=true
```

`contracts/agent-connection.md`를 D에게 공유.

## 되돌리기

- 지식 기반만 내리기: `rag_kb_enabled=false` apply (버킷·인덱스는 남음)
- 인덱스 다시 만들기: Dev Tools(마스터) `DELETE rag-docs` → `setup_opensearch.py` → 재동기화
