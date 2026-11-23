"""OpenSearch 도메인 안 설정을 저장소 정의대로 맞춘다 (specs/a-platform/014-log-opensearch, research R5).

사람(A)이 실행한다. 도메인을 지웠다 다시 만들어도 이 명령 한 번이면 같은 상태가 된다(멱등).

  python setup_opensearch.py --dry-run     # 적용할 것만 출력
  python setup_opensearch.py               # 적용

적용 순서
  1. 인덱스 템플릿 3개 (opensearch/index-templates)
  2. 보관 정책 ISM 2개 (opensearch/ism) — 이미 있으면 seq_no로 갱신
  3. 역할 firehose_writer (opensearch/roles)
  4. 역할 매핑: firehose_writer ← Firehose 역할, readall·opensearch_dashboards_user·reports_writer ← 뷰어 역할
     (reports_writer: 대시보드 PDF·PNG 보고서. 이 도메인에는 기본 reports_full_access가 없어 opensearch/roles에서 만든다)
     (관리자 all_access는 도메인 마스터 = Terraform을 apply한 IAM 사용자라 따로 매핑하지 않음)
  5. 알림 채널(SNS 운영 토픽) + 모니터 errors-burst (opensearch/monitors)
  6. (사람) Dashboards 저장 객체: dashboards/*.ndjson을 Dashboards > Stack Management > Saved objects > Import

요청은 실행하는 사람의 AWS 자격 증명으로 SigV4 서명한다(FGAC 마스터 = 도메인을 만든 A의 IAM 사용자로 실행).
비밀값을 다루지 않는다.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFS = HERE / "opensearch"
REGION = "ap-northeast-2"
DOMAIN = "tms-logs"
ALERT_TOPIC = "tms-collector-alerts"
CHANNEL_ID = "tms-ops-sns"
ROLES = {
    "firehose": "tms-logs-firehose",
    "viewer": "tms-logs-viewer",
    "sns": "tms-logs-sns",
}


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def role_arn(account: str, key: str) -> str:
    return f"arn:aws:iam::{account}:role/{ROLES[key]}"


def plan(account: str) -> list[tuple[str, str, str, dict | None]]:
    """[(설명, 메서드, 경로, 본문)] — 순서대로 적용한다."""
    steps: list[tuple[str, str, str, dict | None]] = []
    for f in sorted((DEFS / "index-templates").glob("*.json")):
        steps.append((f"인덱스 템플릿 {f.stem}", "PUT", f"/_index_template/{f.stem}", load(f)))
    for f in sorted((DEFS / "ism").glob("*.json")):
        steps.append((f"보관 정책 {f.stem}", "ISM", f"/_plugins/_ism/policies/{f.stem}", load(f)))
    for f in sorted((DEFS / "roles").glob("*.json")):
        steps.append((f"역할 {f.stem}", "PUT", f"/_plugins/_security/api/roles/{f.stem}", load(f)))
    mappings = {
        "firehose_writer": [role_arn(account, "firehose")],
        "readall": [role_arn(account, "viewer")],
        "opensearch_dashboards_user": [role_arn(account, "viewer")],
        "reports_writer": [role_arn(account, "viewer")],
    }
    for role, arns in mappings.items():
        steps.append((f"역할 매핑 {role}", "PUT", f"/_plugins/_security/api/rolesmapping/{role}",
                      {"backend_roles": arns, "description": "014 setup_opensearch.py"}))
    channel = {"config_id": CHANNEL_ID, "config": {
        "name": "운영 메일 (tms-collector-alerts)", "config_type": "sns",
        "sns": {"topic_arn": f"arn:aws:sns:{REGION}:{account}:{ALERT_TOPIC}", "role_arn": role_arn(account, "sns")}}}
    steps.append(("알림 채널 SNS", "CHANNEL", f"/_plugins/_notifications/configs/{CHANNEL_ID}", channel))
    for f in sorted((DEFS / "monitors").glob("*.json")):
        steps.append((f"모니터 {f.stem}", "MONITOR", "/_plugins/_alerting/monitors", load(f)))
    return steps


# ---------------------------------------------------------------------------
# HTTP (SigV4)
# ---------------------------------------------------------------------------


class Client:
    def __init__(self, endpoint: str, session):
        from botocore.auth import SigV4Auth

        self.base = f"https://{endpoint}"
        self.creds = session.get_credentials()
        self.signer = SigV4Auth(self.creds, "es", REGION)

    def call(self, method: str, path: str, body: dict | None = None) -> tuple[int, dict]:
        from botocore.awsrequest import AWSRequest

        data = json.dumps(body).encode() if body is not None else None
        req = AWSRequest(method=method, url=self.base + path, data=data,
                         headers={"Content-Type": "application/json"} if data else {})
        self.signer.add_auth(req)
        prepared = urllib.request.Request(req.url, data=data, method=method, headers=dict(req.headers))
        try:
            with urllib.request.urlopen(prepared, timeout=30) as resp:
                text = resp.read().decode() or "{}"
                return resp.status, json.loads(text)
        except urllib.error.HTTPError as e:
            text = e.read().decode() or "{}"
            try:
                return e.code, json.loads(text)
            except ValueError:
                return e.code, {"raw": text[:300]}


def apply_step(c: Client, kind: str, path: str, body: dict) -> str:
    if kind == "PUT":
        status, out = c.call("PUT", path, body)
        return _ok(status, out)
    if kind == "ISM":
        status, cur = c.call("GET", path)
        if status == 200:
            q = f"?if_seq_no={cur['_seq_no']}&if_primary_term={cur['_primary_term']}"
            status, out = c.call("PUT", path + q, body)
            return "갱신 " + _ok(status, out)
        status, out = c.call("PUT", path, body)
        return "생성 " + _ok(status, out)
    if kind == "CHANNEL":
        status, _ = c.call("GET", path)
        if status == 200:
            status, out = c.call("PUT", path, {"config": body["config"]})
            return "갱신 " + _ok(status, out)
        status, out = c.call("POST", "/_plugins/_notifications/configs", body)
        return "생성 " + _ok(status, out)
    if kind == "MONITOR":
        q = {"query": {"match_phrase": {"monitor.name": body["name"]}}}
        status, found = c.call("POST", "/_plugins/_alerting/monitors/_search", q)
        hits = found.get("hits", {}).get("hits", []) if status == 200 else []
        if hits:
            status, out = c.call("PUT", f"/_plugins/_alerting/monitors/{hits[0]['_id']}", body)
            return "갱신 " + _ok(status, out)
        status, out = c.call("POST", path, body)
        return "생성 " + _ok(status, out)
    raise ValueError(kind)


def _ok(status: int, out: dict) -> str:
    if status >= 300:
        raise RuntimeError(f"HTTP {status}: {json.dumps(out, ensure_ascii=False)[:300]}")
    return f"HTTP {status}"


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--endpoint", help="도메인 주소(없으면 describe-domain으로 찾음)")
    p.add_argument("--account", help="계정 ID(없으면 STS로 찾음)")
    p.add_argument("--profile")
    args = p.parse_args(argv)

    session = None
    account = args.account
    if not args.dry_run or not account:
        import boto3

        session = boto3.Session(profile_name=args.profile, region_name=REGION)
        account = account or session.client("sts").get_caller_identity()["Account"]
    steps = plan(account)
    if args.dry_run:
        for i, (desc, kind, path, _) in enumerate(steps, 1):
            print(f"{i:2}. {desc:<36} {kind:<8} {path}")
        print(f"(+) Dashboards 저장 객체: {', '.join(sorted(f.name for f in (HERE / 'dashboards').glob('*.ndjson')))} — 화면에서 가져오기")
        return 0
    endpoint = args.endpoint or session.client("opensearch").describe_domain(DomainName=DOMAIN)["DomainStatus"]["Endpoint"]
    c = Client(endpoint, session)
    for i, (desc, kind, path, body) in enumerate(steps, 1):
        print(f"{i:2}. {desc:<36} {apply_step(c, kind, path, body)}")
    print("다음: Dashboards > Stack Management > Saved objects > Import 로 dashboards/*.ndjson을 가져온다")
    return 0


if __name__ == "__main__":
    sys.exit(main())
