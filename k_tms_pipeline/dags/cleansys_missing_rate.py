from datetime import datetime, timedelta, timezone
from airflow.decorators import dag, task
from airflow.exceptions import AirflowFailException
from cleansys.monitor import KST, build_report, save_report

@ dag(
    dag_id = "cleansys_missing_rate",                               # dag 이름
    schedule = "0 0 * * *",                                         # 실행 주기(매일 00시 00분에 자동 실행)
    start_date = datetime(2026, 10, 29, tzinfo = timezone.utc),     # 과거 실행 시작 날짜
    catchup = True,                                                 # 누락 날짜 실행 설정 
    max_active_runs = 1,                                            # 동시 실행 dag 수 설정
    default_args = {                                                
        "retries": 1,                                               # 재시도 횟수
        "retry_delay": timedelta(minutes = 5),                      # 재시도 전 대기 시간
        "execution_timeout": timedelta(minutes = 10),               # 최대 실행 시간
    },
    tags = ["monitor", "cleansys"], 
)
def cleansys_missing_rate():

    @ task
    def build_and_save(data_interval_end = None) -> dict:
        day = (data_interval_end.astimezone(KST) - timedelta(days = 1)).strftime("%Y-%m-%d")                    # 배치 실행 시각을 KST로 변환 후 하루 전 날짜 문자열 구하기
        report = build_report(day)                                                                             # 어제자 데이터 집계 리포트 생성
        key = save_report(day, report)                                                                          # 생성한 리포트 저장, 저장 경로 전달받음
        return {                                                                                                     # 요약 결과 dict로 반환
            "date": day,
            "report_key": key,
            "missing_slots": report["slots"]["missing_count"],
            "missing_calls": report["calls"]["missing_count"],
            "inspect_fail": report["inspect_fail"],
        }

    @ task
    def check_report(saved: dict) -> None:
        if saved["missing_slots"] > 0:                                                                               # 만약 누락 데이터 슬롯이 존재하면
            raise AirflowFailException(                                                                              
                f"{saved['date']} 슬롯 누락 {saved['missing_slots']}개"
                f"(호출 누락 {saved['missing_calls']}, 점검 실패 {saved['inspect_fail']}) - {saved['report_key']}"
            )

    check_report(build_and_save())

cleansys_missing_rate()