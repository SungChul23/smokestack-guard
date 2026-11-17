'''
- summary test: manifest 집계가 설정한 성분 x 모양 별 에피소드 수와 같은지 확인
'''
from datetime import date
from synth_train import generate, summary

D = date(2026, 11, 16)
def test_summary_matches_config(config, ref_df, tmp_path):
    generate.generate_day(config, ref_df, D, tmp_path)
    table = summary.summarize(tmp_path / "manifest")
    for item, shapes in config["daily_episodes"].items():
        for shape, count in shapes.items():
            assert table[("2026-11-16", item, shape)]["episodes"] == count
            assert table[("2026-11-16", item, shape)]["rows"] > 0

def test_summary_two_days(config, ref_df, tmp_path):
    generate.backfill(config, ref_df, D, date(2026, 11, 17), tmp_path)
    table = summary.summarize(tmp_path / "manifest")
    assert {k[0] for k in table} == {"2026-11-16", "2026-11-17"}
