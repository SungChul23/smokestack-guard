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
