'''
- cycle test: 발행(release) -> spark 적재 한 사이클의 순서, 실패 처리, 잠금, 비밀값 취급을 ㅓㅈㅇ함
'''
from datetime import datetime, timezone
from synth_train import cycle

NOW = datetime(2026, 11, 17, 3, 0, tzinfo = timezone.utc)

# 부른 명령을 기록하고 정해 둔 종료 코드, 출력 등을 돌려주는 가짜 실행기
class FakeRunner:
    def __init__(self, results = None):
        self.calls = []
        self.results = results or {}

    @staticmethod
    def kind(args):
        if args[:2] == ["docker", "start"]:
            return "docker-start"
        if args[:2] == ["docker", "run"]:
            return "docker-run"
        return "release"

    def __call__(self, args, env = None):
        self.calls.append((args, env))
        return self.results.get(self.kind(args), (0, ""))

def make_config(**over):
    c = {
        "config_path": "config/daily.yaml",
        "containers": ["sg-kafka", "k_tms_pipeline-minio-1"],
        "release_bootstrap": "localhost:9092",
        "image": "sg-spark:3.5",
        "network": "sg-net",
        "bootstrap": "kafka:19092",
        "endpoint": "http://host.docker.internal:9000",
        "bucket": "sg-synth-bronze",
        "create_bucket": True,
        "checkpoint": "ckpt_s3",
        "env_file": None,
        "lock_minutes": 30,
        "log_dir": "logs",
    }
    c.update(over)
    return {"cycle": c}

def kinds(runner):
    return [FakeRunner.kind(a) for a, _ in runner.calls]

def log_text(root):
    return next((root / "logs").glob("cycle_*.log")).read_text(encoding = "utf-8")

# 순서: 컨테이너 확인 -> 발행 -> 적재
def test_order(tmp_path):
    r = FakeRunner()
    assert cycle.run_cycle(make_config(), tmp_path, r, now = NOW) == 0
    assert kinds(r) == ["docker-start", "release", "docker-run"]

# 컨테이너 목록이 비면 docker start를 부르지 않음
def test_no_containers_skips_start(tmp_path):
    r = FakeRunner()
    assert cycle.run_cycle(make_config(containers = []), tmp_path, r, now = NOW) == 0
    assert kinds(r) == ["release", "docker-run"]

# 비밀값은 환경 변수로만 넘기고 명령줄, 로그에 남기지 않는다. 필요한 키만 읽는다
def test_secrets_only_in_env(tmp_path):
    env_file = tmp_path / "x.env"
    env_file.write_text("MINIO_ROOT_USER=USERVAL-9f3a\nMINIO_ROOT_PASSWORD=PASSVAL-77c1\nOTHER=zzz\n", encoding="utf-8")
    runner = FakeRunner(results = {"release": (0, "발행 3개 PASSVAL-77c1"), "docker_run": (0, "[batch 0] 3개 기록")})
    assert cycle.run_cycle(make_config(env_file = str(env_file)), tmp_path, runner, now = NOW) == 0
    for args, env in runner.calls:
        assert not any("VAL-" in a for a in args)
    ingest_args, ingest_env = next(c for c in runner.calls if FakeRunner.kind(c[0]) == "docker-run")
    assert ingest_env["MINIO_ROOT_USER"] == "USERVAL-9f3a"
    assert "OTHER" not in ingest_env
    assert "-e" in ingest_args and "MINIO_ROOT_USER" in ingest_args
    assert "VAL-" not in log_text(tmp_path)

# env 파일이 없으면 비밀값 없이 실행
def test_missing_env_file_is_ok(tmp_path):
    r = FakeRunner()
    assert cycle.run_cycle(make_config(env_file = str(tmp_path / "none.env")), tmp_path, r, now = NOW) == 0
    _, env = next(c for c in r.calls if FakeRunner.kind(c[0]) == "docker-run")
    assert not env

# read_env_file은 필요한 키만 읽고 주석, 빈 줄은 건너뜀
def test_read_env_file(tmp_path):
    p = tmp_path / "e.env"
    p.write_text("# 주석\n\nMINIO_ROOT_USER=u\nOTHER=z\nbad line\n", encoding = "utf-8")
    assert cycle.read_env_file(p) == {"MINIO_ROOT_USER": "u"}
    assert cycle.read_env_file(tmp_path / "none.env") == {}

# 발행이 실패하면 적재하지 않고 1 반환
def test_release_failure_stops(tmp_path):
    r = FakeRunner(results = {"release": (1, "boom")})
    assert cycle.run_cycle(make_config(), tmp_path, r, now = NOW) == 1
    assert "docker_run" not in kinds(r)
    assert "release 실패" in log_text(tmp_path)

# 컨테이너 확인이 실패하면 발행도 하지 않음
def test_docker_start_failure_stops(tmp_path):
    r = FakeRunner(results = {"docker-start": (1, "no docker")})
    assert cycle.run_cycle(make_config(), tmp_path, r, now = NOW) == 1
    assert kinds(r) == ["docker-start"]

# 적재가 실패하면 1
def test_ingest_failure(tmp_path):
    r = FakeRunner(results = {"docker-run": (1, "err1\nerr2")})
    assert cycle.run_cycle(make_config(), tmp_path, r, now = NOW) == 1
    assert "적재 실패" in log_text(tmp_path)

# 잠금: 최근 잠금이 있으면 건너뛰고, 오래된 잠금은 무시하며, 끝나면 잠금이 사라짐
def test_lock(tmp_path):
    lock = tmp_path / "run_cycle.lock"
    lock.write_text("")
    r = FakeRunner()
    assert cycle.run_cycle(make_config(), tmp_path, r, now = datetime.now(timezone.utc)) == 0
    assert r.calls == []
    assert lock.exists()

    r2 = FakeRunner()
    future = datetime(2030, 1, 1, tzinfo = timezone.utc)
    assert cycle.run_cycle(make_config(), tmp_path, r2, now = future) == 0
    assert kinds(r2) == ["docker-start", "release", "docker-run"]
    assert not lock.exists()

# 실행기가 예외를 던져도 1을 돌려주고 잠금 해제
def test_runner_exception(tmp_path):
    def boom(args, env = None):
        raise OSError("docker 없음")
    assert cycle.run_cycle(make_config(), tmp_path, boom, now = NOW) == 1
    assert not (tmp_path / "run_cycle.lock").exists()
    assert "OSError" in log_text(tmp_path)

# --lockback-min을 release 명령에 넘기고, 적재 명령에 sink, bucket, endpoint가 들어감
def test_command_args(tmp_path):
    r = FakeRunner()
    cycle.run_cycle(make_config(), tmp_path, r, now = NOW, lookback_min = 3000)
    rel = next(a for a, _ in r.calls if FakeRunner.kind(a) == "release")
    assert rel[rel.index("--lookback-min") + 1] == "3000"
    ing = next(a for a, _ in r.calls if FakeRunner.kind(a) == "docker-run")
    assert ing[ing.index("--sink") + 1] == "s3"
    assert ing[ing.index("--bucket") + 1] == "sg-synth-bronze"
    assert ing[ing.index("--endpoint") + 1] == "http://host.docker.internal:9000"
    assert "--create-bucket" in ing

# endpoint가 비면 --endpoint를 넣지 않고, create_bucket이 false면 --create-bucket도 뺌
def test_aws_style_args(tmp_path):
    r = FakeRunner()
    cycle.run_cycle(make_config(endpoint = None, create_bucket = False), tmp_path, r, now = NOW)
    ing = next(a for a, _ in r.calls if FakeRunner.kind(a) == "docker-run")
    assert "--endpoint" not in ing and "--create-bucket" not in ing