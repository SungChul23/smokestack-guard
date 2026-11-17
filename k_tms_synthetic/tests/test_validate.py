'''
- validate test: 만들어진 파일을 다시 읽어 문제를 잡아내는지 확인
- 먼저 정상 생성 결과가 통과하는지 보고, 일부러 망가뜨린 경우마다 알맞은 검사가 걸리는지 확인한다.
'''
import gzip
import json
import shutil
from synth import generate, validate
from tests.test_generate import sample_config, FIXTURE

# 테스트용 정상 결과 만들기: S-01 에피소드 하나(스냅샷 12개)
def make_out(tmp_path):
    generate.generate(sample_config(), FIXTURE, tmp_path)
    return tmp_path

# 첫 번째 스냅샷 폴더 경로
def first_snapshot_dir(out):
    return sorted((out / "tms_synthetic" / "episode=S-01-E").glob("*/*/*"))[0]

# 첫 스냅샷의 원문을 읽어 mutate 함수로 고친 뒤 다시 저장 (meta·manifest 해시는 그대로 둠)
def rewrite_raw(snap_dir, mutate):
    gz = snap_dir / "snapshot.json.gz"
    data = json.loads(gzip.decompress(gz.read_bytes()))
    mutate(data)
    raw = json.dumps(data, ensure_ascii = False, separators = (",", ":")).encode("utf-8")
    gz.write_bytes(gzip.compress(raw, mtime = 0))

# 걸린 검사 이름 집합
def checks_of(issues):
    return {i["check"] for i in issues}

# 첫 항목(dict) 꺼내기
def first_item(data):
    return data["response"]["body"]["items"][0]

# 정상 생성 결과는 문제 없음
def test_clean_output_passes(tmp_path):
    out = make_out(tmp_path)
    assert validate.validate_out(out) == []

# 확정 표지(_SUCCESS)가 없으면 잡음
def test_detects_missing_success(tmp_path):
    out = make_out(tmp_path)
    (first_snapshot_dir(out) / "_SUCCESS").unlink()
    assert "commit" in checks_of(validate.validate_out(out))

# 원문이 바뀌어 해시가 어긋나면 잡음 (구조는 그대로 유효)
def test_detects_hash_mismatch(tmp_path):
    out = make_out(tmp_path)
    rewrite_raw(first_snapshot_dir(out), lambda s: s["response"]["header"].update(resultMsg = "X"))
    assert "hash" in checks_of(validate.validate_out(out))

# 실측에 없는 필드가 끼면 잡음
def test_detects_extra_field(tmp_path):
    out = make_out(tmp_path)
    rewrite_raw(first_snapshot_dir(out), lambda s: first_item(s).update(extra = "x"))
    assert "fields" in checks_of(validate.validate_out(out))

# 굴뚝 코드가 SYN-으로 시작하지 않으면 잡음
def test_detects_non_syn_code(tmp_path):
    out = make_out(tmp_path)
    rewrite_raw(first_snapshot_dir(out), lambda s: first_item(s).update(stack_code = "1"))
    assert "syn_code" in checks_of(validate.validate_out(out))

# 측정 시각이 30분 격자가 아니면 잡음
def test_detects_off_grid_time(tmp_path):
    out = make_out(tmp_path)
    rewrite_raw(first_snapshot_dir(out), lambda s: first_item(s).update(mesure_dt = "2026-11-20 09:10"))
    assert "grid" in checks_of(validate.validate_out(out))

# 측정값이 소수 둘째 자리 형식이 아니면 잡음
def test_detects_bad_value_format(tmp_path):
    out = make_out(tmp_path)
    rewrite_raw(first_snapshot_dir(out), lambda s: first_item(s).update(nox_mesure_value = "62.4"))
    assert "format" in checks_of(validate.validate_out(out))

# 응답 header의 전체 건수가 실제 항목 수와 다르면 잡음
def test_detects_total_count_mismatch(tmp_path):
    out = make_out(tmp_path)
    rewrite_raw(first_snapshot_dir(out), lambda s: s["response"]["header"].update(totalCount = 5))
    assert "response" in checks_of(validate.validate_out(out))

# 측정값은 있는데 허용기준이 없으면 잡음
def test_detects_half_filled_pair(tmp_path):
    out = make_out(tmp_path)
    rewrite_raw(first_snapshot_dir(out), lambda s: first_item(s).update(nox_exhst_perm_stdr_value = None))
    assert "pairing" in checks_of(validate.validate_out(out))

# 스냅샷 폴더가 하나 빠지면(manifest.jsonl의 수와 다름) 잡음
def test_detects_snapshot_count_mismatch(tmp_path):
    out = make_out(tmp_path)
    shutil.rmtree(first_snapshot_dir(out))
    assert "count" in checks_of(validate.validate_out(out))

# 실측 경로(tms_cleansys)가 out 아래에 생기면 잡음
def test_detects_real_path_folder(tmp_path):
    out = make_out(tmp_path)
    (out / "tms_cleansys").mkdir()
    assert "path" in checks_of(validate.validate_out(out))