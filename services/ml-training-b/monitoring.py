"""A의 RSS/cgroup 계측 로직 재사용. 계측 실패는 학습을 중단하지 않는다."""
import json
import sys
from pathlib import Path, PurePosixPath

def _cgroup_memory() -> dict:
    """현재 Linux 프로세스가 속한 cgroup v1/v2의 사용량·한도를 읽는다."""
    if not sys.platform.startswith("linux"):
        return {"cgroup_status": "not_linux"}
    memberships = []
    for line in Path("/proc/self/cgroup").read_text().splitlines():
        hierarchy, controllers, member = line.split(":", 2)
        if hierarchy == "0" and not controllers:
            memberships.append((2, PurePosixPath(member)))
        elif "memory" in controllers.split(","):
            memberships.append((1, PurePosixPath(member)))
    mounts = Path("/proc/self/mountinfo").read_text().splitlines()
    for version, member in memberships:
        for line in mounts:
            left, right = line.split(" - ", 1)
            fields, info = left.split(), right.split()
            if not (version == 2 and info[0] == "cgroup2") and not (
                version == 1 and info[0] == "cgroup" and "memory" in info[2].split(",")
            ):
                continue
            root = PurePosixPath(fields[3])
            mount = Path(fields[4].replace("\\040", " ").replace("\\134", "\\"))
            if member == PurePosixPath("/"):
                relative = PurePosixPath(".")
            elif member.is_relative_to(root):
                relative = member.relative_to(root)
            else:
                continue
            directory = mount.joinpath(*relative.parts).resolve()
            if not directory.is_relative_to(mount.resolve()):
                continue
            usage, limit = (("memory.current", "memory.max") if version == 2 else
                            ("memory.usage_in_bytes", "memory.limit_in_bytes"))
            if not (directory / usage).is_file() or not (directory / limit).is_file():
                continue
            raw_limit = (directory / limit).read_text().strip()
            return {"cgroup_status": "ok", "cgroup_version": version,
                    "cgroup_path": str(directory),
                    "cgroup_memory_bytes": int((directory / usage).read_text().strip()),
                    "cgroup_limit_bytes": None if raw_limit == "max" else int(raw_limit),
                    "cgroup_limit_raw": raw_limit}
    return {"cgroup_status": "unavailable"}


def _log_memory(stage: str, *, elapsed_seconds=None, include_cgroup=False) -> None:
    """프로세스 현재·누적 최대 RSS를 바이트 단위로 출력한다. 컨테이너 합계는 아니다."""
    try:
        import psutil

        info = psutil.Process().memory_info()
        if sys.platform.startswith("linux"):
            import resource

            peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024
        else:
            peak = getattr(info, "peak_wset", None)
        record = {"event": "memory", "stage": stage,
                  "rss_bytes": info.rss, "peak_rss_bytes": peak}
    except Exception as exc:
        # 계측 실패는 명시적으로 기록하되 학습 결과에는 영향을 주지 않는다.
        record = {"event": "memory_error", "stage": stage, "reason": str(exc)}
    if elapsed_seconds is not None:
        record["elapsed_seconds"] = elapsed_seconds
    if include_cgroup:
        try:
            record.update(_cgroup_memory())
        except Exception as exc:
            record.update(cgroup_status="unavailable", cgroup_error=str(exc))
    try:
        print(json.dumps(record, ensure_ascii=False), flush=True)
    except Exception:
        # 로그 출력 오류도 학습을 중단시키지 않는다.
        pass


