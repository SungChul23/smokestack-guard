"""시험 질문 묶음으로 검색 품질을 채점한다 (spec 016 US3, contracts/ask-cli.md §시험 묶음, SC-003).

  python run_eval.py --kb $RAG_KB_ID [--only e01 m02] [--top 5]

질문마다 ask.py와 같은 검색(rag_query.retrieve: HYBRID + 지목 필터)을 하고
통과 = 상위 N 안에 expect_doc_ids 중 하나(expect_all이면 전부) + forbid_doc_ids가 1위가 아님.
결과 표를 eval_results/<YYYY-MM-DD>.md로 저장한다. 답변 모델은 부르지 않는다(비용 0에 가까움).
"""

from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import yaml

import rag_query as rq

HERE = Path(__file__).resolve().parent
QUESTIONS = HERE / "eval_questions.yaml"
OUT_DIR = HERE / "eval_results"
LEVELS = ("쉬움", "중간", "어려움")


@dataclass
class Graded:
    q: dict
    ok: bool
    ranks: dict[str, int | None]  # 기대 문서별 순위
    top1: str
    why: str


def load_questions(path: Path = QUESTIONS) -> list[dict]:
    qs = yaml.safe_load(path.read_text(encoding="utf-8"))
    ids = [q["id"] for q in qs]
    if len(set(ids)) != len(ids):
        raise ValueError("시험 질문 id 중복")
    for q in qs:
        if q.get("level") not in LEVELS or not q.get("expect_doc_ids"):
            raise ValueError(f"{q.get('id')}: level(쉬움/중간/어려움)·expect_doc_ids 필요")
    return qs


def grade(q: dict, doc_ids: list[str]) -> Graded:
    ranks = {d: (doc_ids.index(d) + 1 if d in doc_ids else None) for d in q["expect_doc_ids"]}
    found = [d for d, r in ranks.items() if r]
    top1 = doc_ids[0] if doc_ids else "-"
    if q.get("expect_all"):
        ok, why = len(found) == len(ranks), "" if len(found) == len(ranks) else "기대 문서 일부 없음"
    else:
        ok, why = bool(found), "" if found else "기대 문서 없음"
    if ok and top1 in q.get("forbid_doc_ids", []):
        ok, why = False, f"금지 문서가 1위({top1})"
    return Graded(q, ok, ranks, top1, why)


def rate(items: list[Graded]) -> str:
    if not items:
        return "-"
    n = sum(g.ok for g in items)
    return f"{n}/{len(items)} ({n / len(items):.0%})"


def report(graded: list[Graded], top: int, kb: str, day: date) -> str:
    lines = [f"# RAG 검색 시험 결과 {day.isoformat()}", "",
             f"지식 기반 `{kb}`, 검색 {rq.SEARCH_TYPE} + 지목 필터, 상위 {top}개 기준.", "",
             "| id | 난이도 | 결과 | 기대 문서 순위 | 1위 문서 | 질문 | 비고 |", "|---|---|---|---|---|---|---|"]
    for g in graded:
        r = ", ".join(f"{d} {n if n else '—'}" for d, n in g.ranks.items())
        lines.append(f"| {g.q['id']} | {g.q['level']} | {'통과' if g.ok else '**실패**'} | {r} | {g.top1} | "
                     f"{g.q['question']} | {g.why or g.q.get('check', '')} |")
    lines += ["", "| 구분 | 통과율 |", "|---|---|"]
    for lv in LEVELS:
        lines.append(f"| {lv} | {rate([g for g in graded if g.q['level'] == lv])} |")
    same = [g for g in graded if "같은 번호" in g.q.get("check", "")]
    fee = [g for g in graded if "산정지수" in g.q.get("check", "")]
    lines += [f"| 같은 번호 별표 | {rate(same)} |", f"| 현행 산정지수 | {rate(fee)} |", f"| **전체** | **{rate(graded)}** |"]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None, rt=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--kb", default=os.environ.get("RAG_KB_ID"))
    p.add_argument("--only", nargs="+")
    p.add_argument("--top", type=int, default=5)
    p.add_argument("--questions", type=Path, default=QUESTIONS)
    p.add_argument("--out", type=Path, default=OUT_DIR)
    a = p.parse_args(argv)
    if not a.kb:
        print("지식 기반 ID가 없습니다: --kb 또는 RAG_KB_ID", file=sys.stderr)
        return 2
    qs = load_questions(a.questions)
    if a.only:
        qs = [q for q in qs if q["id"] in a.only]
    if rt is None:
        import boto3

        rt = boto3.client("bedrock-agent-runtime", region_name=rq.REGION)
    graded = []
    for q in qs:
        res = rq.retrieve(rt, a.kb, q["question"], a.top)
        g = grade(q, [h.doc_id for h in res.hits])
        graded.append(g)
        print(f"{'통과' if g.ok else '실패'} {q['id']} [{q['level']}] 1위 {g.top1:<22} {g.why}")
    text = report(graded, a.top, a.kb, date.today())
    a.out.mkdir(parents=True, exist_ok=True)
    out = a.out / f"{date.today().isoformat()}.md"
    out.write_text(text, encoding="utf-8")
    print(f"\n전체 {rate(graded)} → {out}")
    return 0 if all(g.ok for g in graded) else 1


if __name__ == "__main__":
    sys.exit(main())
