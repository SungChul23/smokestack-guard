'''
- release test: 시계를 주입하고 가짜 발행자로, 도착할 때가 된 스냅샷만 올리는지 확인
'''
from datetime import datetime, timedelta, timezone
import pytest
from synth_train import publish, release

NOW = datetime(2026, 11, 16, 3, 0, tzinfo = timezone.utc)

class FakeProducer:
    def __init__(self):
        self.sent = []
    def produce(self, topic, key = None, value = None, headers = None):
        self.sent.append({"topic": topic, "key": key, "value": value})
    def flush(self):
        return 0

def keys(p):
    return [s["key"].decode() for s in p.sent]

def parse(k):
    return datetime.strptime(k, "%Y%m%dT%H%M%SZ").replace(tzinfo = timezone.utc)

def all_keys(out):
    return [m["key"].decode() for m in publish.messages_from_dir(out)]

# 어제, 오늘, 내일 하루치를 한 번 만들어둔 폴더
@pytest.fixture(scope="module")
def out(config, ref_df, tmp_path_factory):
    path = tmp_path_factory.mktemp("rel")
    release.run(config, ref_df, NOW, path, FakeProducer())
    return path

# run_ts가 지금 이전하고 최근 3시간 안인 스냅샷만 올라감
def test_only_snapshots(config, ref_df, out):
    p = FakeProducer()
    r = release.run(config, ref_df, NOW, out, p)
    ks = keys(p)
    assert ks
    assert all(NOW - timedelta(minutes = 180) < parse(k) <= NOW for k in ks)
    assert any(parse(k) > NOW for k in all_keys(out))
    assert r["last_run_ts"] == max(ks)
    assert r["published"] == len(ks)

# 같은 시각에 두 번 실행해도 결과가 같음(멱등성)
def test_idempotent(config, ref_df, out):
    p1, p2 = FakeProducer(), FakeProducer()
    release.run(config, ref_df, NOW, out, p1)
    r2 = release.run(config, ref_df, NOW, out, p2)
    assert keys(p1) == keys(p2)
    assert [s["value"] for s in p1.sent] == [s["value"] for s in p2.sent]
    assert r2["generated_days"] == []

# 실행을 건너뛴 뒤 다시 실행하면 밀린 것들이 모두 올라감
def test_catch_up_after_skip(config, ref_df, out):
    later = NOW + timedelta(minutes = 90)
    expected = [k for k in all_keys(out) if NOW < parse(k) <= later]
    assert len(expected) >= 3
    p = FakeProducer()
    release.run(config, ref_df, later, out, p)
    assert set(expected) <= set(keys(p))

# 어제, 오늘, 내일 하루치가 없으면 먼저 생성 후 있으면 다시 만들지 않음
def test_generates_missing_days(config, ref_df, tmp_path):
    r = release.run(config, ref_df, NOW, tmp_path, FakeProducer())
    assert r["generated_days"] == ["2026-11-15", "2026-11-16", "2026-11-17"]
    assert release.run(config, ref_df, NOW, tmp_path, FakeProducer())["generated_days"] == []