"""설정 스크립트 (014 T016): 정의 파일이 유효하고, dry-run이 순서대로 적용 목록을 낸다."""

from __future__ import annotations

import json
from pathlib import Path

import setup_opensearch as s

HERE = Path(s.__file__).resolve().parent


def test_definitions_are_valid_json_and_patterns_match():
    for f in (HERE / "opensearch").rglob("*.json"):
        json.loads(f.read_text(encoding="utf-8"))
    pats = {p for f in (HERE / "opensearch/index-templates").glob("*.json") for p in s.load(f)["index_patterns"]}
    assert pats == {"logs-app-*", "logs-pipeline-*", "activity-*"}
    ism = {p for f in (HERE / "opensearch/ism").glob("*.json") for t in s.load(f)["policy"]["ism_template"] for p in t["index_patterns"]}
    assert ism == pats  # 모든 로그 인덱스에 보관 정책이 붙고, 다른 인덱스(나중의 rag-law)에는 안 붙는다


def test_dashboards_ndjson_lines_are_objects():
    for f in (HERE / "dashboards").glob("*.ndjson"):
        for line in f.read_text(encoding="utf-8").splitlines():
            obj = json.loads(line)
            assert obj["type"] in {"index-pattern", "search", "visualization", "dashboard"}


def test_plan_order_and_role_mappings():
    steps = s.plan("123456789012")
    kinds = [k for _, k, _, _ in steps]
    assert kinds.index("ISM") > kinds.index("PUT") and kinds[-1] == "MONITOR" and "CHANNEL" in kinds
    maps = {p.rsplit("/", 1)[-1]: b["backend_roles"] for _, k, p, b in steps if "rolesmapping" in p}
    assert maps["firehose_writer"] == ["arn:aws:iam::123456789012:role/tms-logs-firehose"]
    assert maps["readall"] == maps["opensearch_dashboards_user"] == maps["reports_writer"] == ["arn:aws:iam::123456789012:role/tms-logs-viewer"]
    channel = next(b for _, k, _, b in steps if k == "CHANNEL")
    assert channel["config"]["sns"]["topic_arn"].endswith(":tms-collector-alerts")
    monitor = next(b for _, k, _, b in steps if k == "MONITOR")
    assert monitor["triggers"][0]["actions"][0]["destination_id"] == s.CHANNEL_ID


def test_dry_run_prints_steps(capsys):
    assert s.main(["--dry-run", "--account", "123456789012"]) == 0
    out = capsys.readouterr().out
    assert "인덱스 템플릿 logs-app" in out and "모니터 errors-burst" in out and "ops.ndjson" in out
