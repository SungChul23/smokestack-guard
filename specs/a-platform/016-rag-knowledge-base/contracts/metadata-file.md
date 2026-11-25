# Contract: 문서 메타데이터 파일

Bedrock Knowledge Bases(S3 데이터 소스)가 동기화 때 읽는 파일. 근거: AWS 문서 "Include metadata in a data source" (2026-11-23 확인).

## 위치·이름

- 문서와 **같은 S3 폴더**, 이름 = 문서 전체 파일명 + `.metadata.json`
  - `laws/대기환경보전법시행규칙_별표36_행정처분기준_제71호_20261112.pdf`
  - `laws/대기환경보전법시행규칙_별표36_행정처분기준_제71호_20261112.pdf.metadata.json`
- 파일 하나 **10KB 이하**, UTF-8.
- 문서 버킷의 데이터 소스 폴더에는 PDF와 이 파일만 둔다(다른 파일은 문서로 색인된다).

## 형식

모든 키를 타입을 밝힌 형식으로 쓴다.

```json
{
  "metadataAttributes": {
    "law_name": {
      "value": { "type": "STRING", "stringValue": "대기환경보전법 시행규칙" },
      "includeForEmbedding": true
    },
    "title_ko": {
      "value": { "type": "STRING", "stringValue": "별표 36 행정처분기준" },
      "includeForEmbedding": true
    },
    "part": {
      "value": { "type": "STRING", "stringValue": "별표36" },
      "includeForEmbedding": true
    },
    "effective_date": {
      "value": { "type": "STRING", "stringValue": "2026-11-12" },
      "includeForEmbedding": false
    },
    "effective_ymd": {
      "value": { "type": "NUMBER", "numberValue": 20261112 },
      "includeForEmbedding": false
    },
    "related_articles": {
      "value": { "type": "STRING_LIST", "stringListValue": ["시행규칙 제134조"] },
      "includeForEmbedding": false
    },
    "table_heavy": {
      "value": { "type": "BOOLEAN", "booleanValue": true },
      "includeForEmbedding": false
    }
  }
}
```

## 규칙

| 규칙 | 이유 |
|---|---|
| 타입은 `STRING`, `NUMBER`, `BOOLEAN`, `STRING_LIST`만 | 지식 기반이 허용하는 4종 |
| `null`·빈 문자열·빈 목록 금지 → 키 생략 | 허용 타입이 아님, 거르기 오동작 |
| `includeForEmbedding: true`는 `law_name`, `title_ko`, `part`만 | 같은 번호 별표 구분. 날짜·숫자는 벡터를 흐려서 끔 |
| 키 이름은 영문 소문자·`_` | 인덱스 필드 이름으로 그대로 쓰임 |
| 키 이름 `x-amz-bedrock-kb-` 접두어 금지 | 지식 기반 예약 |
| `effective_ymd`는 시행일이 일까지 확인된 경우만 | 편람(`2024-12`)은 글자만 |

전체 키 목록과 원장 대응은 [data-model.md §2](../data-model.md).

## 검사(check_metadata.py)

PDF마다: 짝 파일 존재 / 이름 정확 / JSON 파싱 / 최상위 `metadataAttributes`만 / 키마다 허용 타입·빈 값 없음 / `includeForEmbedding` 대상 / 필수 키(`doc_id`, `law_name`, `title_ko`, `part`, `doc_type`, `effective_date`, `effective_status`, `authority_class`, `page_count`) / 10KB 이하 / `page_count` = PDF 쪽수 / `doc_id` 유일. 짝 없는 메타데이터 파일, PDF·JSON 외 파일도 실패로 보고.
