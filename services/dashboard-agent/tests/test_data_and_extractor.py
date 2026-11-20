import json
from datetime import datetime

from app.agent.data import JsonDayDataSource
from app.agent.extractor import BedrockExtractor, RuleExtractor
from app.agent.names import Site, SiteResolver
from app.agent.slots import KST

NOW = datetime(2026, 11, 11, 9, 0, tzinfo=KST)


def write_day_dir(root):
    sites = [{"site_id": "100", "source_name": "㈜가나에너지", "boundary_region": "경기도"}]
    (root / "latest.js").write_text(
        "window.TMS_LOCAL="
        + json.dumps({"sites": sites, "stacks": []}, ensure_ascii=False)
        + ";\n",
        encoding="utf-8",
    )
    day = "2026-11-10"
    index = {
        "sites": {"100": [{"path": f"history/100/{day}.json"}]},
        "measurement_time_max": f"{day} 23:30:00",
    }
    (root / "history-index.json").write_text(json.dumps(index), encoding="utf-8")
    (root / "history" / "100").mkdir(parents=True)
    rows = [
        [f"{day} 00:00:00", [["10.5", "100"], [None, None]], 1],
        [f"{day} 00:30:00", [["미수신", "100"], [None, None]], 1],
        [f"{day} 01:00:00", [["1,234.5", "2,000"], [None, None]], 1],
    ]
    chunk = {
        "site_id": "100",
        "stacks": [
            {"stack_id": "KS-x", "facility_id": "f", "stack_code": "7", "observations": rows}
        ],
    }
    (root / "history" / "100" / f"{day}.json").write_text(json.dumps(chunk), encoding="utf-8")


def test_json_day_source_reads_catalogue_and_status_codes(tmp_path):
    write_day_dir(tmp_path)
    data = JsonDayDataSource(tmp_path)
    found = data.find_stacks("(주)가나에너지", "7")
    assert [s.stack_key for s in found] == ["100:7"] and found[0].region == "경기도"
    start = datetime(2026, 11, 10, tzinfo=KST)
    rows = data.observations("100:7", "nox", start, datetime(2026, 11, 11, tzinfo=KST))
    assert [(r.value, r.status_code) for r in rows] == [(10.5, 0), (0.0, 3), (1234.5, 0)]
    sox = data.observations("100:7", "sox", start, datetime(2026, 11, 11, tzinfo=KST))
    assert {r.status_code for r in sox} == {8}
    assert data.as_of() == datetime(2026, 11, 10, 23, 30, tzinfo=KST)


def test_rule_extractor_reads_slots_and_followup():
    extractor = RuleExtractor(SiteResolver([Site("1", "㈜가나에너지", "경기도", "", ("3",))]))
    full = extractor.extract("가나에너지 굴뚝 3 어제 NOx 평균 알려줘", NOW, has_last=False)
    assert full["intent"] == "aggregate" and full["stack"]["code"] == "3"
    assert "가나에너지" in full["stack"]["business"]
    assert full["pollutants"] == ["nox"] and full["time"] == {"kind": "yesterday"}
    assert full["operation"] == "mean" and full["patch"] is None
    follow = extractor.extract("그럼 SOx는?", NOW, has_last=True)
    assert follow["pollutants"] == ["sox"] and follow["patch"] == ["pollutants"]
    assert extractor.extract("오늘 날씨 어때", NOW, has_last=False)["intent"] == "other"
    date = extractor.extract("11월 10일 NOx 최댓값", NOW, has_last=False)
    assert date["time"] == {"kind": "date", "value": "2026-11-10"} and date["operation"] == "max"


class FakeBedrock:
    def __init__(self, tool_input):
        self.tool_input, self.request = tool_input, None

    def converse(self, **request):
        self.request = request
        content = [{"toolUse": {"name": "extract", "input": self.tool_input}}]
        return {"output": {"message": {"content": content}}}


def test_bedrock_extractor_builds_a_forced_tool_request_and_normalizes():
    client = FakeBedrock(
        {
            "kind": "data_query",
            "stack": {"business": "가나에너지", "code": "3"},
            "pollutants": ["NOx"],
            "time": {"kind": "yesterday"},
            "operation": "mean",
            "patch": None,
        }
    )
    extractor = BedrockExtractor(client, "global.anthropic.claude-haiku-4-5-20251001-v1:0")
    out = extractor.extract("어제 3번 굴뚝 NOx 평균", NOW, has_last=False)
    request = client.request
    assert request["toolConfig"]["toolChoice"] == {"tool": {"name": "extract"}}
    assert request["inferenceConfig"]["temperature"] == 0
    assert "2026-11-11" in request["system"][0]["text"]
    assert out["pollutants"] == ["nox"] and out["operation"] == "mean"
    assert out["stack"] == {"business": "가나에너지", "code": "3"}


def test_bedrock_extractor_without_tool_use_is_out_of_scope():
    class Empty:
        def converse(self, **request):
            return {"output": {"message": {"content": [{"text": "응답"}]}}}

    out = BedrockExtractor(Empty(), "m").extract("안녕", NOW, has_last=False)
    assert out == {"intent": "other"}
