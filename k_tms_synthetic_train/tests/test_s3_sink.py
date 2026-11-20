'''
- s3_sink test: s3 호환 저장소에 쓰는 순서, 해시 검증, 경로 제한을 가짜 클라이언트로 확인
'''
import io
import pytest
from datetime import date
from synth_train import generate, ingest_core, publish, s3_sink

D = date(2026, 11, 16)
BUCKET = "sg-synth-bronze"

class FakeS3:
    def __init__(self, corrupt_gz=False):
        self.objects = {}
        self.order = []
        self.corrupt_gz = corrupt_gz
    def put_object(self, Bucket, Key, Body):
        self.objects[(Bucket, Key)] = bytes(Body)
        self.order.append(Key)
    def get_object(self, Bucket, Key):
        data = self.objects[(Bucket, Key)]
        if self.corrupt_gz and Key.endswith(".gz"):
            data = data[:-1] + bytes([data[-1] ^ 1])             # 올라간 파일이 깨진 상황
        return {"Body": io.BytesIO(data)}

@pytest.fixture(scope="module")
def out(config, ref_df, tmp_path_factory):
    path = tmp_path_factory.mktemp("s3")
    generate.generate_day(config, ref_df, D, path)
    return path

def one_message(out):
    m = publish.messages_from_dir(out)[3]
    return ingest_core.message_to_files(m["key"], m["value"], m["headers"])

# 데이터 파일 2개 -> 해시 검증 -> manifest.json -> _SUCCESS 순서
def test_write_order(out):
    prefix, files = one_message(out)
    s3 = FakeS3()
    s3_sink.write_files_s3(s3, BUCKET, prefix, files)
    names = [k.removeprefix(prefix + "/") for k in s3.order]
    assert names == ["snapshot.json.gz", "snapshot.meta.json", "manifest.json", "_SUCCESS"]

# 키는 prefix/파일이름이고 바이트가 그대로 올라간다
def test_keys_and_bytes(out):
    prefix, files = one_message(out)
    s3 = FakeS3()
    s3_sink.write_files_s3(s3, BUCKET, prefix, files)
    for name, data in files.items():
        assert s3.objects[(BUCKET, f"{prefix}/{name}")] == data

# 실측 경로는 거부하고 아무것도 쓰지 않는다
def test_rejects_cleansys():
    s3 = FakeS3()
    with pytest.raises(ValueError):
        s3_sink.write_files_s3(s3, BUCKET, "tms_cleansys/ingest_date=2026-11-16/hour=16/run_ts=20261116T161000Z", {})
    assert s3.objects == {}

# 올라간 원문이 깨졌으면 확정 표지를 쓰지 않는다
def test_no_commit_when_corrupted(out):
    prefix, files = one_message(out)
    s3 = FakeS3(corrupt_gz=True)
    with pytest.raises(ValueError):
        s3_sink.write_files_s3(s3, BUCKET, prefix, files)
    assert (BUCKET, f"{prefix}/_SUCCESS") not in s3.objects
    assert (BUCKET, f"{prefix}/manifest.json") not in s3.objects

# 메시지 48개를 쓰면 파일 모드 산출물과 같은 키·바이트이고, 다시 써도 같다 (멱등)
def test_write_messages_to_s3_equals_file_mode(out):
    msgs = publish.messages_from_dir(out)
    s3 = FakeS3()
    write = lambda prefix, files: s3_sink.write_files_s3(s3, BUCKET, prefix, files)
    assert ingest_core.write_messages_to(msgs, write) == 48
    base = out / "tms_synthetic_train_v2"
    want = {f"tms_synthetic_train_v2/{p.relative_to(base).as_posix()}": p.read_bytes()
            for p in base.rglob("*") if p.is_file()}
    got = {k: v for (b, k), v in s3.objects.items()}
    assert got == want
    ingest_core.write_messages_to(msgs, write)                 
    assert {k: v for (b, k), v in s3.objects.items()} == want