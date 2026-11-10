'''
- 시각표 모듈: 언제 snapshot을 찍고, 어떤 측정 시각의 값을 담을지 정함
- 지연0: 측정 시각이 되자마자 그 값이 snapshot에 나타난다 가정
'''
from datetime import datetime, timedelta, timezone

KST = timezone(timedelta(hours = 9))

# 문자열 날짜, 시각을 KST 시각으로 바꿈
def parse_kst(text: str) -> datetime:
    return datetime.strptime(text, "%Y-%m-%d %H:%M").replace(tzinfo = KST)

# 한국 시각을 실측과 같은 "YYYY-MM-DD HH:MM" 문자열로 변경
def format_mesure_dt(t: datetime) -> str:
    return t.strftime("%Y-%m-%d %H:%M")

# 측정 시각 목록 생성
def mesure_times(start_kst: str, steps: int, slot_min: int = 30) -> list:
    start = parse_kst(start_kst)                                                            # 문자열을 시각 객체로 변환
    return [start + timedelta(minutes = slot_min * i) for i in range(steps)]                          # 시작 시각에 (간격 x 번호)분을 더해 steps개의 시각 생성

# snapshot을 찍는 시각 생성
def snapshot_times(start_kst: str, steps: int, interval_min: int = 10, slot_min: int = 30) -> list:
    start = parse_kst(start_kst)                                                            # 시작 시각 문자열을 시각 객체(KST)로 변형
    count = steps * (slot_min // interval_min)                                                   # snapshot 개수 = 30분 칸 수 x 30분 안에 들어가는 10분 칸 수
    return [start + timedelta(minutes = interval_min * i) for i in range(count)]                      # 시작 시각에서 interval_min분씩 더해 count개의 시각을 생성

# 찍힌 snapshot이 담기 '가장 최근 측정값'이 몇 번째인지 구하기
def latest_slot_index(start_kst: str, snapshot_kst: datetime, slot_min: int = 30) -> int:
    minutes = (snapshot_kst - parse_kst(start_kst)) // timedelta(minutes = 1)                    # snapshot 시각 - 시작 시각 = 시간 차이 <- 1분으로 나눠 분 단위 정수로 변경
    return minutes // slot_min                                                                        # 경과 분을 30분 칸 크기로 나눈 몫을 칸 번호로 사용

# 한국 시각을 UTC로 변경
def to_run_ts(snapshot_kst: datetime) -> datetime:
    return snapshot_kst.astimezone(timezone.utc)

