import json
import os
import time
from pathlib import Path

import httpx

URL = "https://apis.data.go.kr/B552584/cleansys/rltmMesureResult"
KEY = os.environ["DATA_GO_KR_KEY"]

# 응답 원문 저장 폴더
OUT = Path(__file__).parent / "probe_out"
OUT.mkdir(exist_ok=True)

# 호출
def call(page_no = 1, num_rows = 5, **extra):
    params = {
        "serviceKey": KEY,
        "type": "json",
        "pageNo": page_no,
        "numOfRows": num_rows,
        **extra,
    }
    start = time.perf_counter()
    resp = httpx.get(URL, params=params, timeout=30)
    elapsed_ms = int((time.perf_counter() - start) * 1000)
    return resp, elapsed_ms

def summarize(data):
    # 응답에서 헤더/바디/아이템 목록을 꺼낸다. 구조를 아직 모르므로 방어적으로 접근
    resp = data.get("response", data)
    header = resp.get("header", {})
    body = resp.get("body", resp)
    items = body.get("items", [])
    # 일부 API는 items 안에 item 리스트를 한 번 더 감싼다
    if isinstance(items, dict):
        items = items.get("item", [])
    return header, body, items

def classify(items):
    # 측정값 필드에서 숫자가 아닌 문자열이 어떤 것들인지 센다 (결측 표현 파악용)
    from collections import Counter
    odd = Counter()
    for row in items:
        for key, val in row.items():
            if not key.endswith("_mesure_value") or val is None:
                continue
            try:
                float(val)
            except (TypeError, ValueError):
                odd[val] += 1
    return odd

def main():
    from collections import Counter

    # 1) 소량 호출로 헤더와 전체 건수 확인
    resp, ms = call(1, 5)
    data = resp.json()
    header, body, items = summarize(data)
    print("status:", resp.status_code, "| ms:", ms, "| bytes:", len(resp.content))
    print("header:", header)
    print("body keys:", [k for k in body.keys() if k != "items"])
    print("totalCount:", body.get("totalCount"), "| pageNo:", body.get("pageNo"), "| numOfRows:", body.get("numOfRows"))
    print("items returned:", len(items))
    (OUT / "first_call.json").write_bytes(resp.content)

    # 2) numOfRows 상한 확인. 큰 값을 요청해서 실제로 몇 건이 오는지 본다
    resp, ms = call(1, 1000)
    _, body, items = summarize(resp.json())
    print("\n[numOfRows=1000] items returned:", len(items), "| ms:", ms, "| bytes:", len(resp.content))

    # 3) 이 샘플에서 측정시각 분포와 비정상(비숫자) 값 종류
    print("mesure_dt:", Counter(r.get("mesure_dt") for r in items).most_common(5))
    print("non-numeric values:", classify(items).most_common(10))

    # 4) 페이지네이션 동작 확인. 1페이지와 2페이지의 사업장이 겹치지 않는지 비교
    r1 = [(r.get("fact_manage_nm"), r.get("stack_code")) for r in items]
    resp2, _ = call(2, 1000)
    _, _, items2 = summarize(resp2.json())
    r2 = [(r.get("fact_manage_nm"), r.get("stack_code")) for r in items2]
    print("\n[page 2] items:", len(items2), "| overlap with page 1:", len(set(r1) & set(r2)))


if __name__ == "__main__":
    main()
