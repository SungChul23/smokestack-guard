import os
import sys
from datetime import datetime, timezone
# dags 폴더 경로 추가
sys.path.insert(0, "/opt/airflow/dags")
from cleansys.bronze import save_snapshot
from cleansys.client import fetch_snapshot

# 수집, 저장, 결과, 점검 결과 출력
result = fetch_snapshot(os.environ["DATA_GO_KR_KEY"])
print(save_snapshot(result, datetime.now(timezone.utc)))
