import os
from datetime import datetime, timedelta, timezone
from airflow.decorators import dag, task
from airflow.exceptions import AirflowFailException
from cleansys.bronze import stage_snapshot, upload_and_verify, commit_snapshot
from cleansys.client import fetch_snapshot

@dag(
    dag_id = "cleansys_rltm_poll",
    schedule = "*/10 * * * *",                                      # 10분마다 실행
    start_date = datetime(2026, 10, 30, tzinfo = timezone.utc),     # Dag 실행 날짜, 시간 
    catchup = False,                                                # 과거 미실행 구간 skip
    max_active_runs = 1,                                            # 동시 실행 Dag 1개로 제한(동시 실행 방지)
    dagrun_timeout = timedelta(minutes = 8),                        # 8분 초과시 dag 실패 처리
    default_args = {                                                
        "retries": 2,                                               # Task 재시도 최대 2회
        "retry_delay": timedelta(minutes = 1),                      # 재시도 실행 전 1분 대기
        "execution_timeout": timedelta(minutes = 5)                 # 단일 Task 최대 실행시간 5분
    },
    tags = ["bronze", "cleansys"]
)
def cleansys_rltm_poll():

#     @task
#     def fetch_and_store(data_interval_end = None) -> dict:                      # API 호출 및 데이터 저장 작업 Task
#         result = fetch_snapshot(os.environ["DATA_GO_KR_KEY"])      # 환경 변수에서 API Key를 가져와 수집 실행
#         return save_snapshot(result, data_interval_end)                         # 수집 결과, Airflow 배치 실행 완료 시각 S3에 저장

#     @task
#     def check_result(saved: dict) -> None:                                      # 저장된 데이터 유효성 검사 Task
#         inspected = saved["inspect"]                                       
#         if not inspected["ok"]:                                                 # 검증 결과가 False인 경우
#             raise AirflowFailException(                                         # 재시도 없이 Task를 즉시 실패 처리
#                 f"원문 점검 실패: {inspected.get('reason')}"
#                 f"(total = {inspected.get('total_count')}, items = {inspected.get('item_count')})"
#             )

#     check_result(fetch_and_store())     # Task간 의존성

    @task
    def fetch_to_buffer(data_interval_end = None) -> dict:
        result = fetch_snapshot(os.environ["DATA_GO_KR_KEY"])
        return stage_snapshot(result, data_interval_end)

    @task
    def upload_to_s3(buffered: dict, data_interval_end = None) -> dict:
        return upload_and_verify(data_interval_end)

    @task
    def commit(verified: dict, data_interval_end = None) -> None:
        if not commit_snapshot(data_interval_end, verified):
            inspected = verified["inspect"]
            raise AirflowFailException(
                f"원문 점검 실패: {inspected.get('reason')}"
                f"(total = {inspected.get('total_count')}, items = {inspected.get('item_count')})"
            )

    commit(upload_to_s3(fetch_to_buffer()))
cleansys_rltm_poll()                    # Dag 함수 호출 후 Airflow Pipeline 등록