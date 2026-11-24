# Contract: OpenSearch 인덱스 `rag-docs`와 권한

도메인 `tms-logs`(014). 마스터 IAM 사용자가 `setup_opensearch.py`로 만든다(멱등: 있으면 건너뜀, 매핑을 바꿔야 하면 지우고 다시 만든 뒤 재동기화).

## 인덱스 정의 `services/log-search/opensearch/indices/rag-docs.json`

```json
{
  "settings": {
    "index": { "knn": true, "number_of_shards": 1, "number_of_replicas": 0 },
    "analysis": {
      "analyzer": {
        "korean": { "type": "custom", "tokenizer": "nori_tokenizer",
                    "filter": ["nori_part_of_speech", "nori_readingform", "lowercase"] }
      }
    }
  },
  "mappings": {
    "properties": {
      "bedrock-vector": {
        "type": "knn_vector", "dimension": 1024,
        "method": { "name": "hnsw", "engine": "faiss", "space_type": "l2",
                    "parameters": { "m": 16, "ef_construction": 512 } }
      },
      "bedrock-text": { "type": "text", "analyzer": "korean" },
      "bedrock-metadata": { "type": "text", "index": false }
    }
  }
}
```

- **nori는 선택 플러그인이다**: 이 도메인에 기본으로 없어 `analysis-nori` 패키지(2.19 = `G5688189`)를 `tms-log-search`의 `aws_opensearch_package_association`으로 연결한다(블루/그린 배포 1회). 연결 전에는 인덱스 생성이 `failed to find tokenizer under name [nori_tokenizer]`로 실패한다(2026-11-23 확인).
- 복제본 0: 노드 1대(014와 같음).
- 메타데이터 키(`law_name` 등)는 지식 기반이 최상위 필드로 쓰고 동적 매핑된다(글자 = text + keyword). 거르기는 지식 기반 필터가 처리.
- 지식 기반 설정의 필드 이름: 벡터 `bedrock-vector`, 본문 `bedrock-text`, 메타데이터 `bedrock-metadata`.
- 보관 정책(ISM) 없음: 로그 인덱스 패턴(`logs-*`, `activity-*`)과 이름이 겹치지 않는다.

## FGAC 역할 `services/log-search/opensearch/roles/rag_kb_writer.json`

```json
{
  "description": "Bedrock 지식 기반이 rag-docs에 쓰고 검색한다 (016). AWS 문서 권장 목록(kb-osm-permissions-console-fgap) + 매핑 조회. 로그 인덱스 권한 없음",
  "cluster_permissions": [
    "cluster_composite_ops",
    "cluster_monitor",
    "indices:data/read/msearch",
    "indices:data/write/bulk*",
    "indices:data/read/mget*"
  ],
  "index_permissions": [
    {
      "index_patterns": ["rag-docs*"],
      "allowed_actions": [
        "crud",
        "create_index",
        "indices:admin/get",
        "indices:admin/mappings/get",
        "indices:admin/mapping/put",
        "indices:data/read/msearch",
        "indices:data/read/search",
        "indices:data/read/mget*",
        "indices:data/write/index",
        "indices:data/write/update",
        "indices:data/write/delete",
        "indices:data/write/delete/byquery",
        "indices:data/write/bulk*"
      ]
    }
  ],
  "tenant_permissions": []
}
```

- 역할 매핑: `rag_kb_writer` ← `arn:aws:iam::952900391026:role/tms-rag-kb`
- members(`readall`)는 바꾸지 않는다 → Dashboards에서 `rag-docs` 조회만 가능.

## 도메인 접근 정책 (tms-log-search)

기존 주체 목록에 `data "aws_iam_roles"`(`name_regex = "^tms-rag-kb$"`)의 ARN을 더한다. 역할이 없으면 빈 목록이라 apply 순서와 무관하다. 액션 `es:ESHttp*`, 리소스 `<domain_arn>/*`.
