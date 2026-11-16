'''
- ingest_core: Kafka 메시지 하나를 저장 경로, 파일 4개로 바꿈. 
'''
import json
from datetime import datetime, timezone
from synth_train import snapshot, writer

# header: [(이름, 바이트), ...]
def message_to_files(key: bytes, value: bytes, headers) -> tuple:
    h = dict(headers)
    root = h["root"].decode("utf-8")
    episode_id = h["episode_id"].decode("utf-8")
    info = json.loads(h["info"].decode("utf-8"))
    run_ts = datetime.strptime(key.decode("ascii"), "%Y%m%dT%H%M%SZ").replace(tzinfo = timezone.utc)
    prefix = snapshot.build_prefix(episode_id, run_ts, root)
    writer.check_prefix(prefix)
    files = snapshot.make_files(json.loads(value), episode_id, run_ts, info, root)
    return prefix, files

# 메시지 목록을 out_dir 아래에 파일로 쓴다. 쓴 개수를 돌려줌
def write_messages(messages: list, out_dir) -> int:
    for m in sorted(messages, key = lambda m: m["key"]):
        prefix, files = message_to_files(m["key"], m["value"], m["headers"])
        writer.write_files(out_dir, prefix, files)
    return len(messages)