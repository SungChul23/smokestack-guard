"""로컬 에이전트 클라이언트(개발용): LLM 호출을 파일로 주고받는다.

boto3 `bedrock-runtime`의 `converse()`와 같은 모양이라 `BedrockPlanner`·`BedrockExtractor`가
코드 변경 없이 그대로 쓴다. 요청은 `requests/<키>.json`에 쓰고, 로컬 에이전트(Claude Code의
Haiku 서브에이전트)가 읽어 `responses/<키>.json`에 도구 입력(JSON)을 적어 두면 다음 호출부터
그 답을 돌려준다.
답이 아직 없으면 `LocalAgentPending`을 던진다. 해석기와 계획기는 호출 실패를 안전하게 처리한다
(해석기는 정규식 결과로, 계획기는 "질문을 나누지 못했습니다" 안내로).

운영에는 쓰지 않는다. 운영은 같은 자리에 진짜 bedrock-runtime 클라이언트를 넣는다.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


class LocalAgentPending(RuntimeError):
    """로컬 에이전트의 답을 아직 받지 못했다."""

    def __init__(self, key: str) -> None:
        super().__init__(f"로컬 에이전트 답 대기: {key}")
        self.key = key


def request_key(kwargs: dict[str, Any]) -> str:
    """같은 질문·같은 지시면 같은 키(모델 이름은 키에 넣지 않는다)."""
    system = "".join(part.get("text", "") for part in kwargs.get("system", []))
    user = json.dumps(kwargs.get("messages", []), ensure_ascii=False, sort_keys=True)
    tool = kwargs["toolConfig"]["toolChoice"]["tool"]["name"]
    return hashlib.sha256(f"{tool}\n{system}\n{user}".encode()).hexdigest()[:16]


class LocalAgentClient:
    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        (self.root / "requests").mkdir(parents=True, exist_ok=True)
        (self.root / "responses").mkdir(parents=True, exist_ok=True)

    def converse(self, **kwargs: Any) -> dict[str, Any]:
        key = request_key(kwargs)
        tool = kwargs["toolConfig"]["toolChoice"]["tool"]["name"]
        answer = self.root / "responses" / f"{key}.json"
        if answer.exists():
            data = json.loads(answer.read_text(encoding="utf-8"))
            return {
                "output": {"message": {"content": [{"toolUse": {"name": tool, "input": data}}]}}
            }
        request = self.root / "requests" / f"{key}.json"
        if not request.exists():
            schema = next(
                t["toolSpec"]["inputSchema"]["json"]
                for t in kwargs["toolConfig"]["tools"]
                if t["toolSpec"]["name"] == tool
            )
            payload = {
                "id": key,
                "tool": tool,
                "system": "".join(p.get("text", "") for p in kwargs.get("system", [])),
                "user": kwargs["messages"][0]["content"][0]["text"],
                "schema": schema,
            }
            request.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
        raise LocalAgentPending(key)


def pending_requests(root: Path) -> list[Path]:
    """답이 아직 없는 요청 파일 목록."""
    root = Path(root)
    return sorted(
        r for r in (root / "requests").glob("*.json") if not (root / "responses" / r.name).exists()
    )
