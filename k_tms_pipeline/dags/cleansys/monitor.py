import gzip
import json
from datetime import datetime, timedelta, timezone
from .bronze import BUCKET, PREFIX, _hook, put_object

KST = timezone(timedelta(hours = 9))
SLOT_MINUTES = 30
CALL_MINUTES = 10
REPORT_PREFIX = "reports/missing_rate"

# 시간 계산
## KST 시작, 끝 시간을 UTC로 반환
def kst_day_range_utc(day: str) -> tuple[datetime, datetime]:
    start = datetime.strptime(day, "%Y-%m-%d").replace(tzinfo = KST).astimezone(timezone.utc)   # KST 시간 YYYY-MM-DD 문자열을 UTC로 변환
    return start, start + timedelta(days = 1)                                                             # [시작 시간, 끝 시간] 형태 튜플로 반환

## 하루에 모이는 슬롯 개수(30분 단위로 48개)(정상적인 타임 스탬프 목록)
def expected_slots(day: str) -> list[str]:
    start = datetime.strptime(day, "%Y-%m-%d")                              # 'YYYY-MM-DD' 문자열을 날짜 객체로 반환
    return [                                                                          # 하루를 SLOT_MINUTES(30) 단위로 나누어 총 슬롯 개수 구함
        (start + timedelta(minutes = SLOT_MINUTES * i)).strftime("%Y-%m-%d %H:%M")    # 00:00부터 시작해 "YYYY-MM-DD HH:MM" 형태 문자열 리스트 생성
        for i in range(24 * 60 // SLOT_MINUTES)
    ]

## 하루 호출 횟수 (10분씩 144개)
def expected_run_times(day: str) -> list[datetime]:     
    start, _ = kst_day_range_utc(day)                                               # KST 시작시간에 해당하는 UTC 시작 시간을 가져옴
    return [start + timedelta(minutes = CALL_MINUTES * i) for i in range (24 * 60 // CALL_MINUTES)]     # 하루를 CALL_MINUTES(10) 단위로 나누어 총 실행 횟수 구함

## 폴더 이름의 run_ts를 UTC 시각으로 변환
def run_ts_of(run_prefix: str) -> datetime:
    stamp = run_prefix.rsplit("run_ts=", 1)[1]                                      # 폴더명에서 'run_ts=' 바로 뒤에 오는 날짜/시간 문자열만 슬라이싱
    return datetime.strptime(stamp, "%Y%m%dT%H%M%SZ").replace(tzinfo = timezone.utc)   # 추출한 날짜/시간 문자열을 datetime 객체로 변경 후 UTC timezone 부여해 반환


# 저장소 읽기
## 해당 UTC 날짜 아래의 run_ts 폴더 경로를 중복 없이 변환
def list_run_prefixes(ingest_date: str) -> list[str]:
    keys = _hook().list_keys(bucket_name = BUCKET, prefix = f"{PREFIX}/ingest_date={ingest_date}/") or []   # 해당 수집 날짜 폴더 경로 안의 모든 파일 키 목록 조회
    return sorted({k.rsplit("/", 1)[0] for k in keys})                                                                  # 각 파일 경로에서 마지막 파일명을 잘라내 상위 폴더 경로만 추출

## 한개의 폴더 상태와 가장 최신 mesure_dt를 반환
def summarize_run(run_prefix: str) -> dict:
    hook = _hook()
    meta_key = f"{run_prefix}/snapshot.meta.json"                                                   # metadata 파일 경로
    raw_key = f"{run_prefix}/snapshot.json.gz"                                                      # 실제 압축 데이터 파일 경로

    if not hook.check_for_key(meta_key, BUCKET):                                                         # metadata가 존재하지 않으면 메타데이터 누락 상태 반환
        return {"run": run_prefix, "status": "meta_missing", "latest": None}

    meta = json.loads(hook.read_key(meta_key, BUCKET))                                             
    if not meta.get("inspect", {}).get("ok"):                                                            # metadata의 검증(inspect)결과가 ok가 아니면 검증 실패 반환
        return {"run": run_prefix, "status": "inspect_fail", "latest": None}

    if not hook.check_for_key(raw_key, BUCKET):                                                          # 실제 압축 데이터 파일이 없다면 데이터 누락 상태 반환
        return {"run": run_prefix, "status": "raw_missing", "latest": None}

    body = hook.get_key(raw_key, BUCKET).get()["Body"].read()                                       # 압축 데이터 파일 내용 읽어오기
    items = json.loads(gzip.decompress(body))["response"]["body"]["items"]                          # gzip 압축 해제 후 JSON으로 변환해 실제 데이터 items 추출
    latest = max((i["mesure_dt"] for i in items if i.get("mesure_dy")), default = None)      # 데이터 측정날짜가 유효한 항목의 측정시간이 가장 최신인 값 찾기
    return {"run": run_prefix, "status": "ok", "latest": latest}                                         # inspect 상태가 ok인 가장 최신 측정 시각 반환


# 누락률 계산, 저장
## 하루치 누락 보고서 dict 생성
def build_report(day: str) -> dict:
    d = datetime.strptime(day, "%Y-%m-%d")                                                  
    runs = []                                                                                   
    for ingest_date in ((d - timedelta(days = 1)).strftime("%Y-%m-%d"), day):                       # 입력받은 날짜와 그 전날의 수집 날짜 폴더 모두 조회
        runs += list_run_prefixes(ingest_date)

    start, end = kst_day_range_utc(day)                                         # 조회할 KST 날짜의 UTC 시작, 종료 범위 구하기
    summaries = [summarize_run(r) for r in runs]                                        # 가져온 모든 실행 폴더의 metadata, 최신 측정 시각 요약
    in_day = [s for s in summaries if start <= run_ts_of(s["run"]) < end]               # 실행 폴더의 생성 시각이 KST 날짜기준 하루 안에 포함되는 건만 추출

    captured = {s["latest"] for s in summaries if s["status"] == "ok"}                         # 정상 수집(inspect = ok) 데이터 안에서 최신 시각 목록 구하기
    missing_slots = [s for s in expected_slots(day) if s not in captured]                # 계산한 정상 타임스탬프 목록중 안들어온 슬롯 찾기

    present = {run_ts_of(s["run"]) for s in in_day}                                  # 대상 날짜 범위에서 실제 실행된 시간 목록 구하기
    missing_calls = [                                                                    # 안들어온 슬롯을 KST 'HH:MM' 형태로 추출
        t.astimezone(KST).strftime("%H:%M") for t in expected_run_times(day) if t not in present
    ] 

    def count(status: str) -> int:                                                                                              # 상태값 건수 count
        return sum(1 for s in in_day if s["status"] == status)                                                                  

    return {                                                                                                                    # 최종 종합 report dict 형태로 반환
        "target_date_kst": day,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec = "seconds"),
        "folders_in_day": len(in_day),
        "slots": {"expected": len(expected_slots(day)), "missing_count": len(missing_slots), "missing": missing_slots},
        "calls": {"expected": len(expected_run_times(day)), "missing_count": len(missing_calls), "missing": missing_calls},
        "inspect_fail": count("inspect_fail"),
        "meta_missing": count("meta_missing"),
        "raw_missing": count("raw_missing")
    }

# 누락률 보고서를 Json 형식으로 저장 후 저장 경로 반환
def save_report(day: str, report: dict) -> str:
    key = f"{REPORT_PREFIX}/date={day}/report.json"
    put_object(key, json.dumps(report, ensure_ascii = False, indent = 2).encode("utf-8"))
    return key