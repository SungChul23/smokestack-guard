'''
- snapshot 생성: 값들을 실제 API 응답과 똑같은 모양의 파일로 변경
- 저장되는 파일
    - snapshot.json.gz
    - snapshot.meta.json
    - manifest.json
    - _SUCCESS
'''
import gzip
import json
import hashlib
from datetime import timezone

# 측정 항목 7가지 (실제 API 와 같은 순서)
ITEMS = ["nox", "sox", "tsp", "hcl", "co", "nh3", "hf"]

# 합성 데이터를 저장하는 맨 위 폴더
SYNTHETIC_ROOT = "tms_synthetic"

# 측정값 문자열: 소수점 둘쨰 자리.
def format_value(value: float) -> str:
    return f"{value:.2f}"

# 허용기준 문자열: 필요한 만큼만
def format_limit(limit: float) -> str:
    return f"{limit:g}"

# 기준대비율과 허용기준에서 측정값 문자열, 허용기준 문자열을 만듬
def ratio_to_measure(ratio_pct: float, limit: float):
    value = ratio_pct / 100 * limit             # 측정값 역산
    return format_value(value), format_limit(limit)    # 측정값을 소수 둘째자리 문자열, 허용기준은 문자열로 바꿔 반환

# 하나의 항목을 만듬. 실제와 같은 18개 필드
def make_item(area_nm, fact_manage_nm, stack_code, mesure_dt, measures: dict) -> dict:
    unknown = set(measures) - set(ITEMS)                       # ITEMS에 없는 것을 찾음
    if unknown:                                                     # 모르는 이름이 하나라도 있다면 에러로 알림
        raise ValueError(f"모르는 항목 이름: {sorted(unknown)}")

    item = {                                        # 항목과 상관 없는 4가지 필드를 먼저 채움
        "area_nm": area_nm,
        "fact_manage_nm": fact_manage_nm,
        "stack_code": stack_code,
        "mesure_dt": mesure_dt
    }
    for name in ITEMS:                                              # ITEM 항목 7개를 전부 돌아 빠짐없이 필드를 생성 
        value, limit = measures.get(name, (None, None))   # 측정값, 허용기준 넣기, 안넘겼다면 None, None
        item[f"{name}_mesure_value"] = value                        # 실측 필드 이름 규칙대로 측정값과 허용기준을 넣음
        item[f"{name}_exhst_perm_stdr_value"] = limit
    return item

# 항목들을 실제 API 응답 모양으로 감쌈
def make_snapshot(items: list) -> dict:
    return{
        "response": {
            "header": {"resultCode": "0", "totalCount": len(items), "resultMsg": "NORMAL_CODE"}, 
            "body": {"items": items},
        }
    }

# 저장 폴더 경로 (UTC 기준)
def build_prefix(episode_id: str, run_ts) -> str:
    if run_ts.tzinfo is None:                                                   # 시간대 정보가 없는 시각이면 거부.
        raise ValueError("run_ts에는 시간대가 있어야 함")
    t = run_ts.astimezone(timezone.utc)                                    # 어떤 시간대로 들어와도 UTC 시간대로 변경
    return (                                                                    # 경로를 이어 붙임
        f"{SYNTHETIC_ROOT}/episode={episode_id}"                                # 합성 전용 루트 + 에피소드 폴더
        f"/ingest_date={t:%Y-%m-%d}/hour={t:%H}/run_ts={t:%Y%m%dT%H%M%SZ}"      # 날짜/시/실행시각 폴더
    )

# 실제 수집기의 응답 점검과 같은 규칙 (응답 코드가 0이고 전체 건수 = 실제 항목 수)
def inspect_snapshot(snapshot: dict) -> dict:
    header = snapshot["response"]["header"]                                     # 응답 header를 꺼냄. (결과 코드, 전체 건수 확인)
    item_count = len(snapshot["response"]["body"]["items"])                     # 실제로 들어있는 item 개수를 셈
    ok = header["resultCode"] == "0" and header["totalCount"] == item_count     # 정상 조건: 결과 코드가 0이고 header의 건수와 item 실제 건수가 같아야 함
    return {                                                                         # 점검 결과 돌려줌
        "ok": ok,                                                                    # 정상이면 True
        "result_code": header["resultCode"],                                         # 응답이 알려준 결과 코드
        "total_count": header["totalCount"],                                         # 응답 header의 전체 건수
        "item_count": item_count,                                                    # 실제 항목 수
        "reason": None if ok else "resultCode 또는 건수 불일치"                       # 정상이면 None, 아니면 어떤 점검에서 걸렸는지 기술
    }

def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()                                           # 데이터로 64자리 해시를 계산 후 결과를 16진수 글자로 바꿈

# json을 글자 그대로 바이트로 변경
def _json_bytes(obj, **kwargs) -> bytes:
    return json.dumps(obj, ensure_ascii=False, **kwargs).encode("utf-8")              # 객체를 JSON 글자로 바꿈. 완성된 JSON 글자를 UTF-8 바이트로 바꿔 반환

# 먼저 저장할 파일 2개(원문, meta)
def make_data_files(snapshot: dict, episode_id: str, run_ts, info: dict) -> dict:
    raw = _json_bytes(snapshot, separators = (",", ":"))                                # snapshot을 JSON 바이트로 압축 (",", ":")는 공백 제거로 크기를 줄이고, 모양 고정
    gz = gzip.compress(raw, mtime = 0)                                                  # 원문을 gzip으로 압축. header 시각 0 고정
    prefix = build_prefix(episode_id, run_ts)                                             # 저장될 경로 생성
    ts = run_ts.astimezone(timezone.utc).isoformat(timespec = "seconds")                  # run_ts를 UTC로 변환 후 초 단위까지 ISO 문자열로 생성
    meta = {                                                                   # meta 생성
        "source": "synthetic",                                                                 # 합성 데이터 표기
        "run_ts": ts,                                                                          # 실행 시각
        "saved_at": ts,                                                                        # 저장 시각
        "raw_bytes": len(raw),                                                                 # 압축 전 크기
        "gz_bytes": len(gz),                                                                   # 압축 후 크기
        "sha256_raw": _sha256(raw),                                                            # 원문의 지문
        "raw_key": f"{prefix}/snapshot.json.gz",                                               # 원문 파일이 놓일 경로
        "inspect": inspect_snapshot(snapshot),                                                 # 결과 코드 / 건수 점검 결과
        "synthetic": {"episode_id": episode_id, **info},                                       # 합성 생성 위치, 시나리오/비전 등
    }
    return {"snapshot.json.gz": gz, "snapshot.meta.json": _json_bytes(meta, indent = 2)}       # 파일 이름, 내용 반환

# 확정 표지 
def make_commit_files(data_files: dict, run_ts) -> dict:
    meta = json.loads(data_files["snapshot.meta.json"])                                   # meta 파일을 dict로 읽음
    if not meta["inspect"]["ok"]:                                                              # 응답 점검을 통과하지 못한 snapshot에는 확정표지를 작성하지 않음
        raise ValueError("응답 점검 불통으로 인해 확정 표지 생성 불가")                           

    manifest = {                                                               # 확정 표지 내용 (manifest)
        "manifest_version": 1,                                                                 # manifest 버전
        "files": [                                                                             # 데이터 파일 목록(각 파일의 이름, 크기, 지문)
            {"name": name, "bytes": len(data), "sha256": _sha256(data)}
            for name, data in data_files.items()
        ],
        "raw_sha256": meta["sha256_raw"],                                                      # 압축을 풀었을 때의 원문 지문(해시)
        "committed_at": run_ts.astimezone(timezone.utc).isoformat(timespec = "seconds"),       # 확정 시각
    }
    return {"manifest.json": _json_bytes(manifest, indent = 2), "_SUCCESS": b""}               # manifest는 들여쓰기 포함, _SUCCESS 반환

# 총 4개 파일을 한 번에. 테스트와 간단한 편의 함수
def make_files(snapshot: dict, episode_id: str, run_ts, info: dict) -> dict:
    data = make_data_files(snapshot, episode_id, run_ts, info)                           # 데이터 파일 2개 (원문, meta 생성)
    return {**data, **make_commit_files(data, run_ts)}                                         # 위 데이터를 확인해 확정 표지 생성 후 모두 반환
