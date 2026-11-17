'''
- 에피소드 계획 모듈: 설정(config)을 읽어 어떤 에피소드르 만들지 계획표 생성
- 값을 만드는 것이 아닌 이름, 배출구 코드, seed, 시작 시각을 결정
'''
import zlib
import numpy as np
import yaml
from synth import schedule

VALID_ITEMS = {"nox", "sox"}

# config.yaml파일을 읽어 dict 형식으로 만듬
def load_config(path) -> dict:              
    with open(path, encoding = "utf-8") as f:       # 한글 주석이 포함되어 있어 utf-8로 읽기
        return yaml.safe_load(f)                    # 데이터만 읽고 코드를 실행하지 않음

# 에피소드 ID에서 시나리오 번호를 뽑음 ("S-02-E-NOX" -> "S-02")
def scenario_of(episode_id: str) -> str:
    return "-".join(episode_id.split("-")[:2])      # "-"로 쪼갠 후 앞 두 조각만 다시 붙임

# 합성 배출구 코드 생성 ("S-02-E-NOX", 1 -> "SYN-S02ENOX-01")
def make_stack_code(episode_id: str, n: int) -> str:
    return f"SYN-{episode_id.replace('-', '')}-{n:02d}"     # "-"를 빼고, 번호를 두 자리로 채워 이어 붙임

# 성분 목록이 비어 있지 않고, 모르는 성분이 없는지 확인
def _check_items(owner: str, items: list) -> None:
    if not items:
        raise ValueError(f"{owner}: 성분 목록이 비어 있음")
    unknown = set(items) - VALID_ITEMS
    if unknown:
        raise ValueError(f"{owner}: 모르는 성분 {sorted(unknown)}")

# 에피소드 ID 생성: 시나리오 + (변형) + (성분은 성분이 2개 이상일 때)
def make_episode_id(base_id: str, variant, item: str, multi_item: bool) -> str:
    parts = [base_id]
    if variant:
        parts.append(variant)
    if multi_item:
        parts.append(item.upper())
    return "-".join(parts)

# 설정의 시나리오를 개별 에피소드로 펼침
def expand_episodes(episodes_cfg: dict) -> list:
    result = []
    for base_id, spec in episodes_cfg.items():
        if "episodes" in spec:
            for entry in spec["episodes"]:
                items = entry["items"]
                _check_items(base_id, items)
                rising = entry.get("rising", items)
                _check_items(base_id, rising)
                if not set(rising) <= set(items):
                    raise ValueError(f"{base_id}-{entry['suffix']}: rising {rising}이 items{items}에 없음")
                result.append({"episode_id": f"{base_id}-{entry['suffix']}", "variant": None, "items": items, "rising": rising})
        else:
            items = spec["items"]
            _check_items(base_id, items)
            variants = spec.get("variants") or [None]
            multi_item = len(items) > 1
            for variant in variants:
                for item in items:
                    result.append({"episode_id": make_episode_id(base_id, variant, item, multi_item), "variant": variant, "items": [item], "rising": [item]})
    
    ids = [r["episode_id"] for r in result]
    duplicated = {i for i in ids if ids.count(i) > 1}
    if duplicated:
        raise ValueError(f"에피소드 ID가 겹침: {sorted(duplicated)}")
    return result

# 에피소드마다 다른 seed 생성
def make_seed(base_seed: int, episode_id: str) -> int:
    key = zlib.crc32(episode_id.encode("utf-8"))
    return int(np.random.SeedSequence([base_seed, key]).generate_state(1)[0])

# 설정으로 에피소드 계획표 작성
def build_plan(config: dict) -> list:
    run = config["run"]
    try:
        schedule.parse_kst(run["start_kst"])
    except ValueError:
        raise ValueError(f"start_kst가 시각이 아님: {run['start_kst']!r}")

    plans = []
    for ep in expand_episodes(config["episodes"]):
        plans.append({
            "episode_id": ep["episode_id"],
            "scenario_id": scenario_of(ep["episode_id"]),
            "variant": ep["variant"],
            "items": ep["items"],
            "rising": ep["rising"],
            "stack_codes": [make_stack_code(ep["episode_id"], 1)],
            "seed": make_seed(run["seed"], ep["episode_id"]),
            "start_kst": run["start_kst"],
        })
    return plans