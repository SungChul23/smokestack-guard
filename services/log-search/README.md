# log-search

서비스 로그를 OpenSearch로 모아 검색·통계·알림을 한다. 설계: [specs/a-platform/014-log-opensearch](../../specs/a-platform/014-log-opensearch/spec.md)

```
서버·Lambda·Glue 로그(CloudWatch) ─ 구독 필터 ─┐
Step Functions 실행 결과(EventBridge) ────────┼─▶ router.py ─▶ Firehose 3개 ─▶ OpenSearch tms-logs
                                               │   (한 줄씩 풀고 꼬리표·나누기)    logs-app / logs-pipeline / activity
                                               └   실패분 → s3://smokestack-tms-logs-952900391026/failed/
```

| 파일 | 하는 일 |
|---|---|
| `router.py` | 라우터 Lambda. Firehose는 CloudWatch 묶음을 OpenSearch에 직접 못 넣어 여기서 한 줄 = 레코드 하나로 나눈다 |
| `setup_opensearch.py` | 도메인 안 설정(인덱스 템플릿, 보관 14·28일, 역할 매핑, 알림 채널·모니터). 멱등, `--dry-run` |
| `opensearch/` | 위 설정의 정의 파일 |
| `dashboards/*.ndjson` | Dashboards 저장 객체. `ops`·`usage`: 인덱스 패턴·저장 검색, `boards`: 차트 15개와 대시보드 "운영 현황"·"사용 현황"(인덱스 패턴을 넣지 않아 다시 가져와도 필드 목록이 지워지지 않는다). 화면에서 가져온다 |

## RAG 문서 인덱스 `rag-docs` (016)

같은 도메인에 Bedrock 지식 기반의 벡터 저장소 인덱스가 있다. 로그 인덱스와 보관 정책·템플릿이 따로다.

- 정의 `opensearch/indices/rag-docs.json`: `bedrock-vector`(knn 1024, faiss hnsw l2), `bedrock-text`(nori 분석기 — 도메인에 nori 플러그인 패키지 연결 필요, `tms-log-search` 변수 `nori_package_id`), `bedrock-metadata`(색인 안 함).
- FGAC 역할 `opensearch/roles/rag_kb_writer.json`: `rag-docs*`만 읽기·쓰기 + 지식 기반이 요구하는 인덱스·매핑 조회 권한. 지식 기반 서비스 역할 `tms-rag-kb`에 매핑.
- `setup_opensearch.py`는 인덱스가 **없을 때만** 만든다(덮어쓰지 않음). 매핑을 바꾸려면 인덱스를 지우고 다시 만든 뒤 지식 기반 데이터 소스를 다시 동기화한다(임베딩만, 1센트 안팎).
- members(읽기 전용)는 `_mapping`을 볼 수 없다. 확인은 마스터 IAM으로.
- 문서·동기화·질문 도구: [services/rag-docs](../rag-docs/README.md)

## 처음 만들 때 (A)

1. `infra/stacks/tms-log-search` apply (도메인 15~30분)
2. OpenSearch가 만든 Cognito 앱 클라이언트(`AmazonOpenSearchService-tms-logs-…`)에 Google 추가 (spec quickstart §4)
3. 같은 스택을 **한 번 더 apply** → 그 클라이언트에 members 역할 규칙이 붙는다
4. `python setup_opensearch.py --dry-run` → `python setup_opensearch.py` (도메인 마스터 = 1번을 apply한 IAM 사용자로 실행)
5. Dashboards 주소(`terraform output dashboards_url`) → Google 로그인 → 테넌트 **Global** → Dashboards Management > Saved objects > Import로 `dashboards/*.ndjson`
   - 가져온 인덱스 패턴에는 필드 목록이 없다. Index patterns에서 패턴마다 **Refresh field list**를 눌러야 Discover가 열린다(`activity-*`는 첫 활동 로그가 들어온 뒤)
6. 그래프·대시보드는 Dashboards에서 만들고, 다 되면 Saved objects에서 내보내 `dashboards/`에 커밋한다

## 시험

```bash
python3.12 -m venv .venv && .venv/bin/pip install pytest ruff boto3
.venv/bin/python -m pytest -q && .venv/bin/ruff check .
```
