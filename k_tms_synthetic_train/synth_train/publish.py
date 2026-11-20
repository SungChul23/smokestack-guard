'''
- publish: 파일 모드로 만든 스냅샷(out)을 Kafka 메시지로 바꿔 발행
'''
import gzip
import json
from datetime import datetime, timezone
from pathlib import Path
from synth_train import snapshot

TOPIC = "tms.synthetic.train"
RUN_FMT = "%Y%m%dT%H%M%SZ"

# 메시지 하나. 크기가 한도 이상이면 오류
def make_message(raw: bytes, run_ts, info: dict, root: str, episode_id: str = "", max_bytes: int = 1_000_000) -> dict:
    if len(raw) >= max_bytes:
        raise ValueError(f"메시지 크기 {len(raw)}바이트가 한도 {max_bytes}바이트 이상")
    key = run_ts.astimezone(timezone.utc).strftime(RUN_FMT).encode("ascii")
    headers = [
        ("root", root.encode("utf-8")),
        ("episode_id", episode_id.encode("utf-8")),
        ("info", json.dumps(info, ensure_ascii=False).encode("utf-8")),
    ]
    return {"key": key, "value": raw, "headers": headers}

# out아래 확정된(_SUCCESS가 존재하는) 스냅샷 중 since 초과 ~ until 이하의 run_ts를 순서대로 메시지로 만듬
def messages_from_dir(src, root: str = snapshot.TRAIN_ROOT, max_bytes: int = 1_000_000, since = None, until = None) -> list:
    base = Path(src) / root
    pattern = ("ingest_date=*/hour=*/run_ts=*" if root == snapshot.TRAIN_ROOT 
               else "episode=*/ingest_date=*/hour=*/run_ts=*")
    dirs = [d for d in base.glob(pattern) if d.is_dir() and (d / "_SUCCESS").exists()]
    dirs.sort(key = lambda d: d.name)
    msgs = []
    for d in dirs:
        run_ts = datetime.strptime(d.name.removeprefix("run_ts="), RUN_FMT).replace(tzinfo = timezone.utc)
        if (since is not None and run_ts <= since) or (until is not None and run_ts > until):
            continue
        raw = gzip.decompress((d / "snapshot.json.gz").read_bytes())
        synthetic = json.loads((d / "snapshot.meta.json").read_text(encoding = "utf-8"))["synthetic"]
        info = {k: v for k, v in synthetic.items() if k != "episode_id"}
        msgs.append(make_message(raw, run_ts, info, root, synthetic.get("episode_id", ""), max_bytes))
    return msgs

# 메시지들을 생산자로 발행하고 개수를 돌려줌
def publish(producer, topic: str, messages: list) -> int:
    for m in messages:
        while True:
            try:
                producer.produce(topic, key = m["key"], value = m["value"], headers = m["headers"])
                break
            except BufferError:
                producer.poll(1)
        if hasattr(producer, "poll"):
            producer.poll(0)
    left = producer.flush()
    if left:
        raise RuntimeError(f"전송되지 않은 메시지가 {left}개가 남음")
    return len(messages)