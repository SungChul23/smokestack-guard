'''
- cycle: 발행(release) -> spark 적재 한 사이클, 스케줄러
'''
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

KST = timezone(timedelta(hours = 9))
SECRET_KEYS = ("MINIO_ROOT_USER", "MINIO_ROOT_PASSWORD")

# .env에서 필요한 키만 읽음. 파일이 없으면 빈 값
def read_env_file(path, keys = SECRET_KEYS) -> dict:
    p = Path(path)
    if not p.exists():
        return {}
    out = {}
    for line in p.read_text(encoding = "utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not  in line:
            continue
        k, v = line.split("=", 1)
        if k in keys:
            out[k] = v
    return out

# 실제 실행기
def subprocess_runner(args, env = None):
    r= subprocess.run(args, capture_output = True, text = True, encoding = "utf-8",
                       errors = "replace", env={**os.environ, "PYTHONIOENCODING": "utf-8", **(env or {})})
    return r.returncode, (r.stdout or "") + (r.stderr or "")

# 출력에 섞여 온 비밀값을 가림
def _scrub(text: str, secrets) -> str:
    for v in secrets:
        if v:
            text = text.replace(v, "***")
    return text

def _lines(out: str) -> list:
    return [ln.strip() for ln in out.splitlines() if ln.strip()]

# 한 사이클, 종료 코드: 성공 0, 이미 실행중이라 건너뜀 0, 실패 1
def run_cycle(config: dict, root, runner=subprocess_runner, now=None, lookback_min=None) -> int:
    cfg = config["cycle"]
    root = Path(root)
    now = (now or datetime.now(timezone.utc)).astimezone(KST)

    env_file = cfg.get("env_file")
    secrets = read_env_file(root / env_file) if env_file else {}

    log_dir = root / cfg.get("log_dir", "logs")
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / f"cycle_{now:%Y%m%d}.log"

    def log(msg: str) -> None:
        line = f"{now:%Y-%m-%d %H:%M:%S} {_scrub(msg, secrets.values())}"
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(line + "\n")
        print(line)

    # 겹쳐 실행 방지: 잠금이 lock_minutes 안에 만들어졌으면 건너뜀 (오래된 잠금은 비정상 종료로 보고 무시)
    lock = root / "run_cycle.lock"
    if lock.exists():
        age_min = (now.timestamp() - lock.stat().st_mtime) / 60
        if age_min < cfg.get("lock_minutes", 30):
            log("이미 실행 중이라 건너뜀")
            return 0
    lock.write_text("")

    try:
        # 컨테이너 확인 (이미 켜져 있으면 그대로)
        if cfg.get("containers"):
            code, out = runner(["docker", "start", *cfg["containers"]], None)
            if code != 0:
                log(f"컨테이너 확인 실패: {(_lines(out) or ['-'])[-1]}")
                return 1

        # 발행
        rel = [sys.executable, "-m", "synth_train", "release",
               "--config", cfg.get("config_path", "config/daily.yaml"),
               "--bootstrap", cfg.get("release_bootstrap", "localhost:9092")]
        if lookback_min:
            rel += ["--lookback-min", str(lookback_min)]
        code, out = runner(rel, None)
        if code != 0:
            log(f"release 실패: {(_lines(out) or ['-'])[-1]}")
            return 1
        log(f"release: {(_lines(out) or ['-'])[-1]}")

        # Spark 적재
        checkpoint = root / cfg["checkpoint"]
        checkpoint.mkdir(parents=True, exist_ok=True)
        docker = ["docker", "run", "--rm", "--network", cfg["network"],
                  "-v", f"{root.resolve()}:/work", "-v", f"{checkpoint.resolve()}:/ckpt",
                  "-w", "/work", "-e", "PYTHONPATH=/work", "-e", "HOME=/tmp"]
        for key in secrets:
            docker += ["-e", key]                  # 값 없이 이름만: 값은 runner의 env로 전달
        docker += [cfg["image"], "/opt/spark/bin/spark-submit", "--master", "local[2]",
                   "ingest/spark_ingest.py", "--bootstrap", cfg["bootstrap"],
                   "--checkpoint", "/ckpt", "--sink", "s3", "--bucket", cfg["bucket"]]
        if cfg.get("endpoint"):
            docker += ["--endpoint", cfg["endpoint"]]
        if cfg.get("create_bucket"):
            docker += ["--create-bucket"]
        code, out = runner(docker, secrets or None)
        if code != 0:
            log(f"적재 실패: {' | '.join(_lines(out)[-3:]) or '-'}")
            return 1
        batches = [ln for ln in _lines(out) if ln.startswith("[batch")]
        log("적재 완료: " + (" / ".join(batches) if batches else "새 메시지 없음"))
        return 0
    except Exception as e:                         # 실행기가 던진 예외도 실패로 기록
        log(f"실패: {type(e).__name__}: {e}")
        return 1
    finally:
        lock.unlink(missing_ok=True)