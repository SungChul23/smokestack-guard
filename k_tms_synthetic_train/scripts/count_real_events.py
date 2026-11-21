'''
- count_real_events: 실측 CSV에서 사건을 뽑아 모양별 건수를 비교
'''
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from synth_train import real_events

SHAPES = ["OTHER", "SPIKE", "EXCEED", "PLATEAU", "OVER", "GRADUAL"]
SPEC = {
    "OTHER": (2402, 1690, 385, 330),
    "SPIKE":   (663, 663, 196, 196),
    "EXCEED":  (511, 113, 122, 90),
    "PLATEAU": (150, 136, 55, 53),
    "OVER":    (89, 76, 16, 16),
    "GRADUAL": (52, 52, 14, 14)
}

series = real_events.load_series(
    ROOT / "data" / "other_series.csv", "2026-10-30 00:00", "2026-11-12 23:30"
)

events = Counter()
cues = Counter()
for (item, fact, code), ratios in series.items():
    for ev in real_events.extract_events(ratios):
        events[(item, ev["shape"])] += 1
        if ev["cue"]:
            cues[(item, ev["shape"])] += 1

print(f"{'모양':8} {'NOX사건':>10} {'NOX단서':>10} {'SOX사건':>10} {'SOX단서':>10}")
for s in SHAPES:
    got = (events[("NOX", s)], cues[("NOX", s)], events[("SOX", s)], cues[("SOX", s)])
    spec = SPEC[s]
    print(f"{s:8} " + " ".join(f"{g:>5}/{p:<4}" for g, p in zip(got, spec)))
print("(각 칸: 내 결과/spec)")