"""로컬 질문 도구: 지식 기반에서 조각을 찾고, 선택하면 인용 붙은 답변까지 (spec 016 US3, contracts/ask-cli.md).

  python ask.py "현행 질소산화물 배출허용기준은?"            # 조각만 (Retrieve, HYBRID)
  python ask.py "…" --top 8 --status 현행                   # 조각 수, 효력 상태 거르기
  python ask.py "…" --answer [--model haiku|sonnet|<ID>]    # 이름표를 붙여 답변 모델 호출(Converse)
  python ask.py "…" --json

지식 기반 ID: --kb 또는 RAG_KB_ID. 질문이 "시행령 별표 8"처럼 문서를 지목하면 그 문서 안에서 찾는다(rag_query).
A의 PC에서만 쓴다. 에이전트(D)는 rag_query의 같은 규칙을 따른다(contracts/agent-connection.md).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time

import rag_query as rq

PREVIEW = 200


def clients(region: str = rq.REGION):
    import boto3

    return boto3.client("bedrock-agent-runtime", region_name=region), boto3.client("bedrock-runtime", region_name=region)


def format_hits(res: rq.Result, secs: float) -> str:
    lines = [f"질문: {res.question}  (조각 {len(res.hits)}개, {secs:.1f}초)"]
    if res.targets:
        lines.append("지목: " + " / ".join(t.label() for t in res.targets)
                     + ("  → 결과 없어 필터 없이 다시 찾음" if res.fallback else ""))
    lines.append("")
    for h in res.hits:
        m = h.meta
        lines.append(f"#{h.rank:<2} 점수 {h.score:.3f}  {m.get('law_name', '?')} · {m.get('part', '?')} · "
                     f"{m.get('effective_date', '?')} · {m.get('effective_status', '?')}")
        lines.append(f"    파일 {h.file}" + (f"  쪽 {h.pages}" if h.pages else ""))
        body = " ".join(h.text.split())
        lines.append(f"    {body[:PREVIEW]}{'…' if len(body) > PREVIEW else ''}")
    return "\n".join(lines)


def format_answer(res: rq.Result, ans: dict) -> str:
    lines = ["", "답변:", ans["text"].strip(), "", "근거:"]
    for h in res.hits:
        lines.append(f"[{h.rank}] {h.cite()}" + (f" — 쪽 {h.pages}" if h.pages else ""))
    lines.append(f"\n(모델 {ans['model']}, 토큰 입력 {ans['tokens_in']:,} / 출력 {ans['tokens_out']:,})")
    return "\n".join(lines)


def error_message(e: Exception, kb: str) -> tuple[str, int]:
    from botocore.exceptions import ClientError, NoCredentialsError, PartialCredentialsError

    if isinstance(e, (NoCredentialsError, PartialCredentialsError)):
        return f"AWS 자격 증명을 찾을 수 없습니다 (프로필·리전 {rq.REGION} 확인)", 2
    if isinstance(e, ClientError):
        code = e.response.get("Error", {}).get("Code", "")
        op = getattr(e, "operation_name", "?")
        if code == "ResourceNotFoundException":
            return f"지식 기반 {kb}를 찾을 수 없습니다 (리전·apply 확인)", 3
        if code in ("AccessDeniedException", "AccessDenied", "UnauthorizedException"):
            return f"권한 없음: {op} ({code})", 3
        return f"AWS 오류: {op} ({code}) {e.response.get('Error', {}).get('Message', '')}", 3
    raise e


def main(argv: list[str] | None = None, make_clients=clients) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("question")
    p.add_argument("--kb", default=os.environ.get("RAG_KB_ID"))
    p.add_argument("--top", type=int, default=5)
    p.add_argument("--status", action="append", help="effective_status 거르기 (현행/구판/과거, 여러 번 가능)")
    p.add_argument("--answer", action="store_true", help="답변 + 인용")
    p.add_argument("--model", default=os.environ.get("RAG_ANSWER_MODEL"), help="haiku(기본)·sonnet·추론 프로필 ID")
    p.add_argument("--json", action="store_true")
    a = p.parse_args(argv)
    if not a.kb:
        print("지식 기반 ID가 없습니다: --kb 또는 RAG_KB_ID", file=sys.stderr)
        return 2
    if not 1 <= a.top <= 20:
        print("--top은 1~20", file=sys.stderr)
        return 2
    rt, br = make_clients()
    t0 = time.time()
    try:
        res = rq.retrieve(rt, a.kb, a.question, a.top, a.status)
        ans = rq.answer(br, res, a.model) if a.answer else None
    except Exception as e:  # noqa: BLE001 — 알려진 오류만 메시지로, 나머지는 다시 던짐
        msg, code = error_message(e, a.kb)
        print(msg, file=sys.stderr)
        return code
    secs = time.time() - t0
    if a.json:
        out = {"question": res.question, "targets": [t.label() for t in res.targets], "fallback": res.fallback,
               "hits": [{"rank": h.rank, "score": h.score, "doc_id": h.doc_id, "file": h.file, "pages": h.pages,
                         "cite": h.cite(), "target": h.target, "metadata": h.meta, "text": h.text} for h in res.hits]}
        if ans:
            out["answer"] = ans
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 0
    print(format_hits(res, secs))
    if ans:
        print(format_answer(res, ans))
    return 0


if __name__ == "__main__":
    sys.exit(main())
