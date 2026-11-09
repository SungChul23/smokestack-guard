'''
- 통계 읽기 test
- 확인 항목
    - 쓸 수 없는 굴뚝(값이 변하지 않는 굴뚝, 측정 개수 부족 등)을 제대로 걸러내는지
    - '정상', '정해진 모양' 시나리오 조건으로 후보를 맞게 줄이는가
    - 같은 시드로 뽑으면 항상 같은 굴뚝이 나오는가 (재현성)
'''
from pathlib import Path
from synth import stats
import numpy as np
import pytest

SAMPLE = Path(__file__).parent / "fixtures" / "ref_stats_sample.csv"    # 테스트용 작은 csv 
REAL = Path(__file__).parents[1] / "data" / "ref_stats.csv"             # 진짜 통계 CSV

# B(값 안 변함), C(개수 부족), D(허용기준 변동), F(phi 없음)는 빠지고 A, E, G, H만 남음
def test_usable_excludes_bad_rows():
    df = stats.usable(stats.load_ref_stats(SAMPLE), min_valid = 200)                # 샘플 CSV를 읽고, 쓸 수 없는 굴뚝 거르기
    assert sorted(df["fact_manage_nm"]) == ["사업장A", "사업장E", "사업장G", "사업장H"]         # 남은 사업장 이름을 정렬해서 쓸 수 있는 A, E, G, H만 남았는지 확인

# 정상 조건(평균 10~50, phi 0.5~0.95, p99<80): A와 G만 통과. E(평균 70)와 H(평균 58)는 탈락
def test_normal_filter():
    df = stats.usable(stats.load_ref_stats(SAMPLE))                                 # 샘플 CSV를 읽고, 쓸 수 있는 굴뚝만 남김
    cond = {"mean": [10, 50], "phi": [0.5, 0.95], "p99_max": 80}               # 정상 조건(평균 10~50%, 자기상관(phi) 0.5~0.95, 상위 99%값이 80% 미만)
    assert sorted(stats.filter_normal(df, cond)["fact_manage_nm"]) == ["사업장A", "사업장G"]    # 조건에 맞는 굴뚝 이름을 정렬해서, A, G만 남았는지 확인

# 정해진 모양 조건: 첫 값이 62일 때, 평균에서 표준편차의 2배 이내 + p99<80. H만 통과
def test_trajectory_filter():
    df = stats.usable(stats.load_ref_stats(SAMPLE))                                 # 샘플 CSV를 읽고, 쓸 수 있는 굴뚝만 남김
    cond = {"p99_max": 80, "first_value_within_sigma": 2.0}                    # 정해진 조건: 상위 99%값이 80% 미만, 첫 값이 굴뚝 평균에서 표준편차의 2배 이내
    got = stats.filter_trajectory(df, first_value = 62, cond = cond)                # 정해진 모양의 첫 값이 62%일 때, 조건에 맞는 굴뚝만 남김
    assert list(got["fact_manage_nm"]) == ["사업장H"]                                          # H만 남았는지 확인

# 같은 시드일 때 항상 같은 굴뚝, 후보 안에서만 뽑음
def test_pick_is_reproducible():
    df = stats.usable(stats.load_ref_stats(SAMPLE))                                 # 샘플 CSV를 읽고, 쓸 수 있는 굴뚝만 남김
    first = stats.pick_one(df, np.random.default_rng(1))                            # 시드를 똑같이 1로 설정 후 굴뚝을 2번 뽑음
    second = stats.pick_one(df, np.random.default_rng(1))       
    assert first["fact_manage_nm"] == second["fact_manage_nm"]                                 # 같은 시드 두 번 다 같은 굴뚝이 뽑혀야 함
    assert first["fact_manage_nm"] in set(df["fact_manage_nm"])                                # 뽑힌 굴뚝은 후보 후보 안에 있는 굴뚝이여야 함

# 후보가 하나도 없다면 조용히 넘어가지 않고 에러 발생
def test_pick_from_empty_raises():
    df = stats.usable(stats.load_ref_stats(SAMPLE))                                             # 샘플 CSV를 읽고, 쓸 수 있는 굴뚝만 남김
    empty = stats.filter_normal(df, {"mean": [90, 100], "phi": [0.5, 0.95], "p99_max": 80})     # 평균이 90~100%인 굴뚝만 고르면, 샘플에 하나도 없어 후보가 빔
    with pytest.raises(ValueError):                                                                        # 후보가 없을 때 pick_one이 조용히 넘어가지 않고 ValueError를 내보내는지 확인
        stats.pick_one(empty, np.random.default_rng(1))

@pytest.mark.skipif(not REAL.exists(), reason = "진짜 ref_stats.csv가 없으면 건너뜀")           # 샘플이 아닌 실제 통계 CSV파일이 없으면 "건너뜀 처리"
def test_real_csv_usable_count():                                                              
    assert len(stats.usable(stats.load_ref_stats(REAL))) == 2985                               # 진짜 CSV를 읽어 쓸 수 있는 굴뚝만 남기고, 그 개수가 2985개 인지 확인(현재 CSV 기준, 추후 변경 예정)