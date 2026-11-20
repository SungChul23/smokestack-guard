'''
- publish test: 파일 모드 산출물을 Kafka 메시지로 바꾸는 부분을 브로커 없이 확인
'''
import gzip
import json
import pytest
from datetime import date, datetime, timezone
from synth_train import generate, publish

D = date(2026, 11, 16)

class FakeProducer:
    def __init__(self):
        self.sent = []
    def produce(self, topic, key = None, value = None, headers = None):
        self.sent.append({"topic": topic, "key": key, "value": value, "headers": headers})
    def flush(self):
        return 0

@pytest.fixture(scope = "module")
def out(config, ref_df, tmp_path_factory):
    path = tmp_path_factory.mktemp("pub")
    generate.generate_day(config, ref_df, D, path)
    return path

# 스냅샷 48개가 run_ts순서의 메시지가 되고, 값은 원문 그대로
def test_messages_from_dir(out, config):
    msgs = publish.messages_from_dir(out)
    assert len(msgs) == 48
    keys = [m["key"] for m in msgs]
    assert keys == sorted(keys)
    first_dir = sorted((out / "tms_synthetic_train_v2").glob("ingest_date=*/hour=*/run_ts=*"), key=lambda d: d.name)[0]
    assert msgs[0]["key"].decode() == first_dir.name.removeprefix("run_ts=")
    assert msgs[0]["value"] == gzip.decompress((first_dir / "snapshot.json.gz").read_bytes())
    headers = dict(msgs[0]["headers"])
    info = json.loads(headers["info"])
    assert info["generator_version"] == config["run"]["generator_version"]
    assert info["stats_version"] == config["run"]["stats_version"]
    assert headers["root"] == b"tms_synthetic_train_v2"
    assert headers["episode_id"] == b""

# 메시지 크기가 한도를 넘으면 오류
def test_message_too_large():
    with pytest.raises(ValueError):
        publish.make_message(b"x" * 10, datetime(2026, 11, 16, tzinfo = timezone.utc), {}, "tms_synthetic_train_v2", max_bytes = 5)

# 발행하면 토픽, 순서대로 생산자에게 전달
def test_publish_sends_in_order(out):
    msgs = publish.messages_from_dir(out)
    producer = FakeProducer()
    assert publish.publish(producer, "tms.synthetic.train", msgs) == 48
    assert [s["key"] for s in producer.sent] == [m["key"] for m in msgs]
    assert {s["topic"] for s in producer.sent} == {"tms.synthetic.train"}

# 시각 범위로 고름
def test_messages_time_range(out):
    msgs = publish.messages_from_dir(out)
    keys = [m["key"].decode() for m in msgs]
    def parse(k):
        return datetime.strptime(k, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
    since, until = parse(keys[10]), parse(keys[20])
    part = publish.messages_from_dir(out, since=since, until=until)
    assert [m["key"].decode() for m in part] == keys[11:21]