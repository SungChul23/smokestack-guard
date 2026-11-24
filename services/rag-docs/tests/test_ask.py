"""rag_query · ask · run_eval 시험 (spec 016 US3, T029·T032). AWS를 부르지 않는다(가짜 클라이언트)."""

from __future__ import annotations

import json

import pytest
from botocore.exceptions import ClientError, NoCredentialsError

import ask
import rag_query as rq
import run_eval

SIHAENG = "대기환경보전법 시행령"
GYUCHIK = "대기환경보전법 시행규칙"


def chunk(doc_id: str, law: str, part: str, text: str, score: float = 0.5, **meta) -> dict:
    m = {"doc_id": doc_id, "law_name": law, "part": part, "title_ko": f"{part[:2]} {part[2:]} 제목",
         "effective_date": "2026-11-12", "effective_status": "현행", **meta}
    return {"content": {"text": text}, "score": score, "metadata": m,
            "location": {"s3Location": {"uri": f"s3://bucket/laws/{doc_id}.md"}}}


class FakeRuntime:
    """filter에 따라 다른 결과를 돌려주는 가짜 bedrock-agent-runtime."""

    def __init__(self, by_part: dict[str | None, list[dict]], error: Exception | None = None):
        self.by_part = by_part
        self.calls: list[dict] = []
        self.error = error

    def retrieve(self, knowledgeBaseId, retrievalQuery, retrievalConfiguration):
        if self.error:
            raise self.error
        vc = retrievalConfiguration["vectorSearchConfiguration"]
        self.calls.append(vc)
        part = None
        for c in [vc.get("filter", {})] + vc.get("filter", {}).get("andAll", []):
            if c.get("equals", {}).get("key") == "part":
                part = c["equals"]["value"]
        return {"retrievalResults": self.by_part.get(part, [])[: vc["numberOfResults"]]}


class FakeBedrock:
    def __init__(self):
        self.sent = None

    def converse(self, **kw):
        self.sent = kw
        return {"output": {"message": {"content": [{"text": "답 [1]"}]}},
                "usage": {"inputTokens": 100, "outputTokens": 10}}


# --- 지목 찾기 ------------------------------------------------------------------


@pytest.mark.parametrize("q,want", [
    ("시행령 별표 8과 시행규칙 별표 8은 각각?", [(SIHAENG, "별표8"), (GYUCHIK, "별표8")]),
    ("시행령 별표 1의3 사업장 분류", [(SIHAENG, "별표1의3")]),
    ("관제센터 규정 별표 1의 무효자료", [(rq.TMS_CENTER, "별표1")]),
    ("시험검사법 시행규칙 별표 3 정도검사", [(f"{rq.ENV_TEST} 시행규칙", "별표3")]),
    ("별표 36 행정처분", [(None, "별표36")]),
    ("시행규칙 제15조는?", [(GYUCHIK, "본문")]),
    ("제9조에 따라", []),
    ("방지시설 고장 방치 처분", []),
])
def test_find_targets(q, want):
    assert [(t.law_name, t.part) for t in rq.find_targets(q)] == want


def test_target_law_names_exist_in_catalog():
    import catalog as cat

    names = {d.row["law_name"] for d in cat.read_catalog()}
    assert {name for _, name in rq._LAW_WORDS} <= names


# --- 검색 -----------------------------------------------------------------------


def test_retrieve_always_hybrid_and_merges_targets_alternately():
    rt = FakeRuntime({
        "별표8": [chunk("x", SIHAENG, "별표8", f"t{i}") for i in range(5)],
    })
    res = rq.retrieve(rt, "KB", "시행령 별표 8과 시행규칙 별표 8은?", top=5)
    assert all(c["overrideSearchType"] == "HYBRID" for c in rt.calls)
    assert len(rt.calls) == 4  # 지목마다 한 번 + 현행만 + 필터 없음
    assert rt.calls[2]["filter"] == {"in": {"key": "effective_status", "value": ["현행"]}}
    assert "filter" not in rt.calls[-1]
    f0 = rt.calls[0]["filter"]["andAll"]
    assert {"equals": {"key": "law_name", "value": SIHAENG}} in f0
    assert [h.rank for h in res.hits] == list(range(1, len(res.hits) + 1))
    assert len({h.text for h in res.hits}) == len(res.hits)  # 같은 조각은 한 번만


def test_retrieve_marks_fallback_when_targets_empty():
    rt = FakeRuntime({None: [chunk("a", GYUCHIK, "별표36", "본문")]})
    res = rq.retrieve(rt, "KB", "시행령 별표 99는?", top=5)
    assert res.fallback and [h.doc_id for h in res.hits] == ["a"]
    assert "filter" not in rt.calls[-1]


def test_retrieve_status_filter_combines_with_target():
    rt = FakeRuntime({"별표36": [chunk("a", GYUCHIK, "별표36", "본문")]})
    rq.retrieve(rt, "KB", "별표 36", top=3, statuses=["현행"])
    flt = rt.calls[0]["filter"]["andAll"]
    assert {"in": {"key": "effective_status", "value": ["현행"]}} in flt


def test_hit_pages_from_markers_and_cite():
    h = rq._hit(chunk("a", GYUCHIK, "별표8", "앞 <!-- 쪽 3 --> 가 <!-- 쪽 4 --> 나",
                      title_ko="별표 8 대기오염물질의 배출허용기준"), None)
    assert h.pages == "3~4"
    assert h.cite() == "대기환경보전법 시행규칙 별표 8 대기오염물질의 배출허용기준 (2026-11-12 시행, 현행)"
    assert h.file == "laws/a.md"


# --- 답변 -----------------------------------------------------------------------


def test_answer_sends_metadata_headers_and_caveat():
    rt = FakeRuntime({None: [chunk("hb", "굴뚝 원격감시체계 업무편람", "본문", "편람 본문",
                                   effective_status="구판", caveat="부과금 숫자 인용 금지")]})
    res = rq.retrieve(rt, "KB", "부과금은?", top=5)
    br = FakeBedrock()
    out = rq.answer(br, res, "sonnet")
    assert br.sent["modelId"] == rq.MODELS["sonnet"]
    user = br.sent["messages"][0]["content"][0]["text"]
    assert "[1] 굴뚝 원격감시체계 업무편람" in user and "구판" in user and "주의: 부과금 숫자 인용 금지" in user
    assert out["tokens_in"] == 100 and out["text"] == "답 [1]"


# --- ask.py 명령 ----------------------------------------------------------------


def _ask(argv, rt, br=None):
    return ask.main(argv, make_clients=lambda: (rt, br or FakeBedrock()))


def test_ask_output_lines(capsys):
    rt = FakeRuntime({None: [chunk("a", GYUCHIK, "별표36", "<!-- 쪽 2 --> " + "가" * 300, 0.734)]})
    assert _ask(["방치하면 처분은?", "--kb", "KB"], rt) == 0
    out = capsys.readouterr().out
    assert "#1  점수 0.734  대기환경보전법 시행규칙 · 별표36 · 2026-11-12 · 현행" in out
    assert "파일 laws/a.md  쪽 2" in out and out.rstrip().endswith("…")


def test_ask_answer_and_json(capsys):
    rt = FakeRuntime({None: [chunk("a", GYUCHIK, "별표36", "본문")]})
    assert _ask(["질문", "--kb", "KB", "--answer"], rt) == 0
    out = capsys.readouterr().out
    assert "답변:" in out and "근거:\n[1] " in out
    assert _ask(["질문", "--kb", "KB", "--json"], rt) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["hits"][0]["doc_id"] == "a" and "answer" not in data


@pytest.mark.parametrize("argv,code,msg", [
    (["q"], 2, "지식 기반 ID가 없습니다"),
    (["q", "--kb", "KB", "--top", "21"], 2, "--top은 1~20"),
])
def test_ask_argument_errors(argv, code, msg, capsys, monkeypatch):
    monkeypatch.delenv("RAG_KB_ID", raising=False)
    assert _ask(argv, FakeRuntime({})) == code
    assert msg in capsys.readouterr().err


@pytest.mark.parametrize("err,code,msg", [
    (NoCredentialsError(), 2, "자격 증명을 찾을 수 없습니다"),
    (ClientError({"Error": {"Code": "AccessDeniedException", "Message": "x"}}, "Retrieve"), 3, "권한 없음: Retrieve"),
    (ClientError({"Error": {"Code": "ResourceNotFoundException", "Message": "x"}}, "Retrieve"), 3, "지식 기반 KB를 찾을 수 없습니다"),
])
def test_ask_aws_errors(err, code, msg, capsys):
    assert _ask(["q", "--kb", "KB"], FakeRuntime({}, error=err)) == code
    assert msg in capsys.readouterr().err


# --- run_eval -------------------------------------------------------------------


def test_grade_rules():
    q = {"id": "m01", "level": "중간", "question": "?", "expect_doc_ids": ["r8"], "forbid_doc_ids": ["d8"]}
    assert run_eval.grade(q, ["x", "r8"]).ok
    assert not run_eval.grade(q, ["d8", "r8"]).ok  # 금지 문서 1위
    assert not run_eval.grade(q, ["x"]).ok
    both = {**q, "expect_doc_ids": ["d8", "r8"], "expect_all": True, "forbid_doc_ids": []}
    assert run_eval.grade(both, ["d8", "r8"]).ok and not run_eval.grade(both, ["d8"]).ok


def test_questions_file_is_15_balanced_and_ids_in_catalog():
    import catalog as cat

    qs = run_eval.load_questions()
    assert len(qs) == 15
    assert {lv: sum(q["level"] == lv for q in qs) for lv in run_eval.LEVELS} == {"쉬움": 5, "중간": 5, "어려움": 5}
    ids = {d.doc_id for d in cat.read_catalog()}
    for q in qs:
        assert set(q["expect_doc_ids"]) | set(q.get("forbid_doc_ids", [])) <= ids, q["id"]


def test_run_eval_writes_report(tmp_path):
    qf = tmp_path / "q.yaml"
    qf.write_text("- {id: a, level: 쉬움, question: 별표 36, expect_doc_ids: [r36]}\n"
                  "- {id: b, level: 중간, question: 별표 8, expect_doc_ids: [r8], forbid_doc_ids: [d8], check: 같은 번호 별표 구분}\n",
                  encoding="utf-8")
    rt = FakeRuntime({"별표36": [chunk("r36", GYUCHIK, "별표36", "a")],
                      "별표8": [chunk("d8", SIHAENG, "별표8", "b"), chunk("r8", GYUCHIK, "별표8", "c")]})
    code = run_eval.main(["--kb", "KB", "--questions", str(qf), "--out", str(tmp_path)], rt=rt)
    report = next(tmp_path.glob("*.md")).read_text(encoding="utf-8")
    assert code == 1
    assert "| a | 쉬움 | 통과 | r36 1 | r36 |" in report
    assert "| b | 중간 | **실패** |" in report and "금지 문서가 1위(d8)" in report
    assert "| 같은 번호 별표 | 0/1 (0%) |" in report and "| **전체** | **1/2 (50%)** |" in report


def test_retrieve_puts_current_docs_before_old_handbook():
    """현행만 검색한 줄이 먼저 자리를 얻는다: 구판 편람이 상위를 차지해도 현행 근거가 들어온다."""

    class Rt(FakeRuntime):
        def retrieve(self, knowledgeBaseId, retrievalQuery, retrievalConfiguration):
            vc = retrievalConfiguration["vectorSearchConfiguration"]
            self.calls.append(vc)
            if "filter" in vc:  # 현행만
                return {"retrievalResults": [chunk("appx-07", "고시", "별표7", f"현행{i}") for i in range(5)]}
            return {"retrievalResults": [chunk("handbook", "편람", "본문", f"구판{i}", effective_status="구판")
                                         for i in range(5)]}

    res = rq.retrieve(Rt({}), "KB", "정도검사 주기는?", top=5)
    assert [h.doc_id for h in res.hits] == ["appx-07", "handbook", "appx-07", "handbook", "appx-07"]
    rt = Rt({})
    rq.retrieve(rt, "KB", "정도검사 주기는?", top=5, statuses=["구판"])
    assert len(rt.calls) == 1  # --status를 주면 현행 줄을 섞지 않는다
