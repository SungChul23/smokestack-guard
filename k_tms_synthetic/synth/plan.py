'''
- 에피소드 계획 모듈: 설정(config)을 읽어 어떤 에피소드르 만들지 계획표 생성
- 값을 만드는 것이 아닌 이름, 배출구 코드, seed, 시작 시각을 결정
'''
import numpy as np
import yaml
from synth import schedule

S02_VARIANTS = {"NOX": ["nox"], "SOX": ["sox"], "NOXSOX": ["nox", "sox"]}

# config.yaml파일을 읽어 dict 형식으로 만듬
def load_config(path) -> dict:
    with open(path, encoding = "utf-8") as f:       # 한글 주석이 포함되어 있어 utf-8로 읽기
        return yaml.safe_load(f)                    # safe_load: 데이터만 읽고 코드는 실행하지 않음ㅇ

# 에피소드 ID에서 시나리오 번호를 뽑음 ("S-02-E-NOX" -> "S-02")
def scenario_of(episode_id: str) -> str:
    return "-".join(episode_id.split("-")[:2])      # "-"로 쪼갠 후 앞 두 조각만 다시 붙임

# 합성 배출구 코드 생성
def make_stack_code(episode_id: str, n: int) -> str:
    return f"SYN-{episode_id.replace('-', '')}-{n:02d}"     # episode_id의 "-"을 빼고(S-01-E -> S01E), 번호는 두 자리로 채워(1 -> 01) 이어 붙임

# 설정의 시나리오 개수를 개별 에피소드로 펼침
def expand_episodes(episodes_cfg: dict) -> list:
    result = []                                                             # 결과를 쌓을 빈 목록
    for base_id, count in episodes_cfg.items():                                   # 설정의 항목을 하나씩 돈다. 
        if base_id == "S-02-E":                                                   # S-02는 서서히 상승 시나리오로 NOX, SOX, NOX+SOX 3가지 로 나뉨
            if count != 3:                                                        # 개수가 3이 아니라면 설정이 잘못된 것. 에러로 알림
                raise ValueError("S-02는 3(NOX, SOX, NOX+SOX)이여야 함")
            for suffix, items in S02_VARIANTS.items():                            # 변형마다 "S-02-E-NOX"같이 접미사를 붙여 하나의 에피소드 생성
                result.append((f"{base_id}-{suffix}", items))
        else:                                                                     # 나머지 시나리오는 에피소드가 각 1개씩, 항목은 NOX 하나
            if count != 1:                                                        # 1이 아니면 설정 오류
                raise ValueError(f"{base_id}의 개수는 1이어야 함: {count}")
            result.append((base_id, ["nox"]))
    return result

# 에피소드마다 다른 seed를 생성. 같은 base_seed, index면 항상 같은 값
def make_seed(base_seed: int, index: int) -> int:
    return int(np.random.SeedSequence([base_seed, index]).generate_state(1)[0])

# 설정으로 에피소드 계획표 작성
def build_plan(config: dict) -> list:
    run = config["run"]                                                             # 설정에서 실행 공통 부분(seed, 시작 시각 등)을 꺼냄
    try:                                                                                 # 시작 시각 문자열이 올바른 시각인지 확인
        schedule.parse_kst(run["start_kst"])
    except ValueError:
        raise ValueError(f"start_kst가 시각이 아님: {run['start_kst']!r}")

    plans = []                                                                     # 에피소드별 계획서를 쌓을 빈 목록
    for index, (episode_id, items) in enumerate(expand_episodes(config["episodes"])):    # 11개 에피소드를 번호와 함께 하나씩 돌음
        plans.append({                                                                   # 에피소드 하나의 계획서(dict)를 만들어 목록에 추가
            "episode_id": episode_id,                                                      
            "scenario_id": scenario_of(episode_id),
            "items": items,
            "stack_codes": [make_stack_code(episode_id, 1)],
            "seed": make_seed(run["seed"], index),
            "start_kst": run["start_kst"],
        })
    return plans