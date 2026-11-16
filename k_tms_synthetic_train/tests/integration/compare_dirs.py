'''
- compare_dirs: 두 폴더가 경로와 바이트까지 같은지 비교한다
- 실행: python tests/integration/compare_dirs.py out_check/tms_synthetic_train out_kafka/tms_synthetic_train
'''
import sys
from pathlib import Path

def tree(root) -> dict:
    root = Path(root)
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob("*") if p.is_file()}

def main(a, b) -> int:
    ta, tb = tree(a), tree(b)
    only_a = sorted(set(ta) - set(tb))
    only_b = sorted(set(tb) - set(ta))
    differ = sorted(p for p in set(ta) & set(tb) if ta[p] != tb[p])
    print(f"파일 {len(ta)}개 vs {len(tb)}개 | A에만 {len(only_a)} | B에만 {len(only_b)} | 내용 다름 {len(differ)}")
    for label, items in (("A에만", only_a), ("B에만", only_b), ("다름", differ)):
        for p in items[:10]:
            print(f"  [{label}] {p}")
    ok = not (only_a or only_b or differ)
    print("같음" if ok else "다름")
    return 0 if ok else 1

if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2]))