'''
- Bronze에 저장된 데이터를 읽어, 슬롯의 누락률을 계산함
'''
import argparse
import gzip
import json
from datetime import datetime, timedelta, timezone
import boto3
from botocore.exceptions import ClientError

PREFIX = "tms_cleansys"                         # S3 Bronze 데이터 저장 최상위 경로
SLOT_MINUTES = 30                               # API 데이터 갱신 주기
SLOTS_PER_DAY = 48                              # 하루 기대 슬롯 수
EXPECTED_CALLS = 144                            # 10분 주기 호출의 하루 기대 횟수
KST = timezone(timedelta(hours = 9))            # 한국 시간대 변경
s3 = boto3.client("s3")                    # s3 접속 도구
cloudwatch = boto3.client("cloudwatch")    # Cloudwatch 접속 도구

# 정상치 설정(하루/30분 단위로 슬롯을 생성)
def expected_slots(day: str) -> list[str]:
    start = datetime.strptime(day, "%Y-%m-%d")                              # 문자열 날짜를 날짜 객체로 변환
    return [                                                                          # 0 ~ 47번 슬롯 생성
        (start + timedelta(minutes = SLOT_MINUTES * i)).strftime("%Y-%m-%d %H:%M")
        for i in range(SLOTS_PER_DAY)
    ]

# 시간대 맞추기
## KST날짜에 걸쳐있는 UTC 날짜 범위 추출
def utc_dates_for_kst_day(day: str) -> list[str]:
    d = datetime.strptime(day, "%Y-%m-%d")      # 문자열 날짜를 datetime 객체로 변환
    return [
        (d - timedelta(days = 1)).strftime("%Y-%m-%d"),   # 어제 날짜를 계산 후 "YYYY-MM-DD" 형식 문자열로 변환
        d.strftime("%Y-%m-%d"),                           # 당일 날짜를 "YYYY-MM-DD" 형식 문자열로 변환
    ]

## KST 날짜의 시작 시간, 끝 시간을 UTC Timezone으로 변환해 (시작 UTC, 끝 UTC)튜플 형태로 반환
def kst_day_range_utc(day: str) -> tuple[datetime, datetime]:
    start = datetime.strptime(day, "%Y-%m-%d").replace(tzinfo = KST).astimezone(timezone.utc)   # 날짜를 datetime객체로 변환(00:00:00) 후 Timezone 정보를 KST(UTC + 9)로 지정, 이를 UTC 기준 시각으로 변환
    return start, start + timedelta(days =1)                                                              # UTC 기준 시작 시간, 종료 시각을 Tuple로 반환

# S3 폴더 목록 읽기
def list_run_prefixes(bucket: str, ingest_date: str)-> list[str]:
    prefix = f"{PREFIX}/ingest_date={ingest_date}"                  # 검색할 S3 상위 경로 생성
    runs = set()                                                    # 중복 폴더 경로 제거를 위한 집합 
    paginator = s3.get_paginator("list_objects_v2")                 # S3 목록 조회를 위한 페이징 객체 
    for page in paginator.paginate(Bucket = bucket, Prefix = prefix):    # 해당 경로 아래 모든 파일 목록 페이지 단위 반복 조회
        for obj in page.get("Contents", []):                             # 페이지 내 파일이 존재하는 경우 파일 객체 순회
            runs.add(obj["Key"].rsplit("/", 1)[0])                       # obj["Key"]: 파일의 전체 s3 경로, rsplit("/", 1)[0]: 경로 오른쪽 첫 번째 "/"기준으로 잘라 폴더 경로만 추출해 집합에 추가
    return sorted(runs)                                                  # 중복 제거된 폴더 경로를 정렬 후 리스트 반환

# 파일 읽기/형 변환
## json 파일을 읽어 dict로 반환
def read_json(bucket: str, key: str) -> dict:
    body = s3.get_object(Bucket = bucket, Key = key)["Body"].read() # s3 파일을 불러온 후 불러온 데이터의 내용을 읽음
    return json.loads(body)                                              # 읽은 json 파일을 dict 형태로 반환

## gzip 내부 json 파일을 dict로 반환
def read_json_gz(bucket: str, key: str) -> dict:
    body = s3.get_object(Bucket = bucket, Key = key)["Body"].read() # s3 파일을 불러온 후 불러온 데이터의 내용을 읽음 
    return json.loads(gzip.decompress(body))                             # gzip 형태의 파일을 압축 해제 후 dict 형태로 반환

# 폴더 요약
def summarize_run(bucket: str, run_prefix: str) -> dict:
    # 메타데이터 읽기
    try:
        meta = read_json(bucket, f"{run_prefix}/snapshot.meta.json")
    except ClientError:
        return {"run": run_prefix, "status": "meta_missing", "latest": None}    # 파일이 s3에 없는 경우 (파일 누락)

    # 메타 데이터 형식이 {"inspect", {"ok", True}} 형태가 아니라면 수집 실패
    if not meta.get("inspect", {}).get("ok"):
        return {"run": run_prefix, "status": "inspect_fail", "latest": None}    

    # 실제 압축 데이터 파일 읽기 (snapshot.json.gz)
    try:
        data = read_json_gz(bucket, f"{run_prefix}/snapshot.json.gz")
    except ClientError:
        return {"run": run_prefix, "status": "raw_missing", "latest": None}    # 파일이 s3에 없는 경우 (파일 누락)

    items = data["response"]["body"]["items"]                             # Json 데이터 내부에서 데이터 목록(item) 추출
    # item내 각 항목의 mesure_at 값 중 가장 최신 시간 추출 (mesure_at이 없으면 제외, item이 비어있으면 None)
    latest = max(                                                  
        (i["mesure_dt"] for i in items if i.get("mesure_dt")),
        default = None
    )
    return {"run": run_prefix, "status": "ok", "latest": latest}               # 모든 검증을 통과한 정상 상태(ok) 반환

# 누락률 계산, 출력
def report(bucket: str, day: str) -> None:
    runs = []                                                                          # 실행 폴더 목록을 담을 리스트
    for d in utc_dates_for_kst_day(day):                                                     # KST 기준 2개의 걸쳐있는 UTC 순회
        runs += list_run_prefixes(bucket, d)                                                  

    summaries = [summarize_run(bucket, r) for r in runs]                         # 수집된 모든 폴더를 순회하며 메타데이터, 상태요약 객체 리스트 생성

    captured = {s["latest"] for s in summaries if s["status"] == "ok"}                  # 정상 처리건에서("ok") 'latest' 슬롯만 추출해 집합(set)으로 저장

    expected = expected_slots(day)                                                # 해당 KST 날짜에 정상 처리되었을 '슬롯 전체 목록' 가져오기
    missing = [slot for slot in expected if slot not in captured]                 # 정상 처리 기대 슬롯 중 실제 수집 완료된 집합에 없는 슬롯들을 누락 목록으로 생성

    # 특정 상태값을 가진 폴더 개수 count 해주는 함수 
    def count(status: str) -> int:                                                           
        return sum(1 for s in summaries if s["status"] == status)

    print(f"[슬롯 누락률] 대상 날짜(KST): {day}")
    print(f"읽은 폴더 수: {len(runs)}")
    print(f"저장된 슬롯: {SLOTS_PER_DAY - len(missing)} / {SLOTS_PER_DAY}")
    print(f"누락 슬롯 수: {len(missing)}  (누락률 {len(missing) / SLOTS_PER_DAY:.1%})")
    print(f"점검 실패 폴더: {count('inspect_fail')}")
    print(f"메타 없는 폴더: {count('meta_missing')}")
    print(f"원본 없는 폴더: {count('raw_missing')}")
    print("누락 슬롯:", ", ".join(missing) if missing else "없음")

# 슬롯이 왜 비었는지 확인 
def lambda_metric_sum(function_name: str, metric: str, start: datetime, end: datetime) -> int:
    res = cloudwatch.get_metric_statistics(                             # cloudwatch에서 metric 통계 데이터를 가져옴
        Namespace = "AWS/Lambda",                                            
        MetricName = metric,
        Dimensions = [{"Name": "FunctionName", "Value": function_name}],
        StartTime = start,
        EndTime = end, 
        Period = 86400,
        Statistics = ["Sum"]
    )
    return int(sum(p["Sum"] for p in res["Datapoints"]))                      # 반환된 데이터 포인트에서 각 구간의 Sum 값을 모두 더한 후 점수로 반환

# 특정 날짜의 Lambda 함수 지표 불러오기
def report_calls(function_name: str, day: str) -> None:
    start, end = kst_day_range_utc(day)                             # KST 기준 날짜 문자열을 cloudwatch 조회에 필요한 UTC 시작, 종료 datetime 범위 변환
    invocations = lambda_metric_sum(function_name, "Invocations", start, end)      # 해당 기간 동안의 전체 호출 횟수 집계
    errors = lambda_metric_sum(function_name, "Errors", start, end)                # 해당 기간 동안의 에러 수 집계
    throttles = lambda_metric_sum(function_name, "Throttles", start, end)          # 해당 기간 동안의 슬로틀링 횟수 집계

    print(f"\n[Lambda 호출 현황] {function_name}")
    print(f"기대 호출 수: {EXPECTED_CALLS}")
    print(f"실제 호출 수: {invocations}  (부족분 {max(EXPECTED_CALLS - invocations, 0)})")
    print(f"오류 수: {errors}")
    print(f"동시 실행 제한으로 거부된 수: {throttles}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description = "Bronze 슬롯 누락률 계산")            
    parser.add_argument("--bucket", required = True, help = "S3 버킷 이름")
    parser.add_argument("--date", required = True, help = "KST 기준 날짜 (YYYY-MM-DD)")
    parser.add_argument("--function", help = "Lambda 함수 이름")
    args = parser.parse_args()

    report(args.bucket, args.date)
    if args.function:
        report_calls(args.function, args.date)