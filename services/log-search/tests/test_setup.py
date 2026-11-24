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
    assert ism == pats  # 모든 로그 인덱스에 보관 정책이 붙고, RAG 인덱스 rag-docs(016)에는 안 붙는다


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


# --- 016 RAG 인덱스 ---------------------------------------------------------


def test_rag_index_definition():
    body = s.load(HERE / "opensearch/indices/rag-docs.json")
    props = body["mappings"]["properties"]
    assert body["settings"]["index"]["knn"] is True
    assert props["bedrock-vector"]["dimension"] == 1024  # Titan V2, tms-rag embedding_dimensions와 같아야 함
    assert props["bedrock-vector"]["method"]["engine"] == "faiss"
    assert props["bedrock-text"]["analyzer"] == "korean"
    assert body["settings"]["analysis"]["analyzer"]["korean"]["tokenizer"] == "nori_tokenizer"
    assert props["bedrock-metadata"]["index"] is False
    # 로그 보관 정책이 rag-docs에 붙지 않는다
    for f in (HERE / "opensearch/ism").glob("*.json"):
        for t in s.load(f)["policy"]["ism_template"]:
            assert not any(p.startswith("rag") for p in t["index_patterns"])


def test_rag_role_only_touches_rag_index_and_is_mapped_to_kb_role():
    role = s.load(HERE / "opensearch/roles/rag_kb_writer.json")
    assert [p for ip in role["index_permissions"] for p in ip["index_patterns"]] == ["rag-docs*"]
    steps = s.plan("123456789012")
    maps = {p.rsplit("/", 1)[-1]: b["backend_roles"] for _, k, p, b in steps if "rolesmapping" in p}
    assert maps["rag_kb_writer"] == ["arn:aws:iam::123456789012:role/tms-rag-kb"]
    order = [d for d, _, _, _ in steps]
    assert order.index("인덱스 rag-docs") < order.index("역할 rag_kb_writer") < order.index("역할 매핑 rag_kb_writer")
    assert order.index("보관 정책 logs-14d") < order.index("인덱스 rag-docs")


class FakeClient:
    def __init__(self, exists: bool):
        self.exists = exists
        self.calls: list[tuple[str, str]] = []

    def call(self, method, path, body=None):
        self.calls.append((method, path))
        if method == "HEAD":
            return (200 if self.exists else 404), {}
        return 200, {"acknowledged": True}


def test_index_step_never_overwrites_existing_index():
    body = s.load(HERE / "opensearch/indices/rag-docs.json")
    c = FakeClient(exists=True)
    assert s.apply_step(c, "INDEX", "/rag-docs", body) == "있음(건너뜀)"
    assert c.calls == [("HEAD", "/rag-docs")]
    c = FakeClient(exists=False)
    assert s.apply_step(c, "INDEX", "/rag-docs", body).startswith("생성")
    assert c.calls == [("HEAD", "/rag-docs"), ("PUT", "/rag-docs")]


def test_rag_role_can_read_mapping():
    # 지식 기반은 만들 때 인덱스 매핑을 읽어 필드를 검사한다(2026-11-23 indices:admin/mappings/get 없이 거부됨)
    role = s.load(HERE / "opensearch/roles/rag_kb_writer.json")
    acts = set(role["index_permissions"][0]["allowed_actions"])
    # AWS 문서 권장 목록 전부 + 매핑 조회 (2026-11-23 indices:admin/get 빠져 동기화가 권한 실패)
    aws_index = {"indices:admin/get", "indices:data/read/msearch", "indices:data/read/search",
                 "indices:data/write/index", "indices:data/write/update", "indices:data/write/delete",
                 "indices:data/write/delete/byquery", "indices:data/write/bulk*",
                 "indices:admin/mapping/put", "indices:data/read/mget*"}
    assert aws_index | {"indices:admin/mappings/get"} <= acts
    assert {"indices:data/read/msearch", "indices:data/write/bulk*",
            "indices:data/read/mget*"} <= set(role["cluster_permissions"])
