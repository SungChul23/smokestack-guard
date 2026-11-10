'''
- 합성 snapshot 파일을 디스크에 쓰기 
- 실제 수집기가 하는 순서 그대로 따라가기
'''
import gzip
import hashlib
import json
from pathlib import Path
from synth.snapshot import SYNTHETIC_ROOT

DATA_NAMES = ["snapshot.json.gz", "snapshot.meta.json"]  # 데이터 파일
COMMIT_NAMES = ["manifest.json", "_SUCCESS"]            # 검증 (확정 표지) 파일

# 쓰기 경로가 합성 경로인지 확인
def check_prefix(prefix: str) -> None:
    parts = prefix.split("/")       # "/"기준으로 조각내 검사
    ok = (
        parts[0] == SYNTHETIC_ROOT             # 첫 조각이 tms_synthetic이여아 함
        and ".." not in parts                  # 위 폴더로 빠져나가는 경로 금지
        and "" not in parts                    # 빈 조각 금지
    )
    if not ok:
        raise ValueError(f"합성 경로(tms_synthetic/)가 아니여서 쓰지 않음: {prefix}")

# 디스크에 쓴 원문을 다시 읽어 meta의 해시와 같은지 확인
def _verify_data(base: Path) -> None:
    raw = gzip.decompress((base / "snapshot.json.gz").read_bytes())                 # 쓴 gzip 파일을 다시 읽어 압축을 풀어 원문 바이트 확인
    meta = json.loads((base / "snapshot.meta.json").read_text(encoding = "utf-8"))    # meta 파일을 읽어 dict로 만듬
    if hashlib.sha256(raw).hexdigest() != meta["sha256_raw"]:                              # meta의 hash와 원문의 hash를 비교
        raise ValueError("원문 해시가 meta와 다름. 확정표지를 작성하지 않음")

# 파일 묶음을 out_dir/prefix/ 아래에 작성
def write_files(out_dir, prefix: str, files: dict, commit: bool = True) -> Path:
    check_prefix(prefix)                                                                # 쓰기전에 접두어(prefix) 확인
    base = Path(out_dir) / prefix                                                 # 실제 폴더 경로 = 출력 폴더 + 접두어
    base.mkdir(parents = True, exist_ok = True)                                         # 폴더가 없으면 중간 폴더까지 한번에 만듬
    for name in DATA_NAMES:                                                             # 데이터 파일(gzip, meta)을 먼저 작성.
        (base / name).write_bytes(files[name])

    _verify_data(base)                                                                  # 데이터 파일이 온전한지 다시 읽어 확인

    if commit:                                                                          # commit이 True일 떄만 확정표지 작성
        for name in COMMIT_NAMES:
            (base / name).write_bytes(files[name])
    return base                                                                         # 경로 반환