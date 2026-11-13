"""상태 머신 정의 (T022). spec 008 FR-012·013, research R8."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

ASL = Path(__file__).resolve().parents[3] / "infra/stacks/tms-silver/ktms_pipeline.asl.json"


@pytest.fixture(scope="module")
def states() -> dict:
    text = ASL.read_text(encoding="utf-8")
    for name in ("silver_job", "ml_ready_job", "topic_arn", "bucket"):
        assert f"${{{name}}}" in text
        text = text.replace(f"${{{name}}}", f"fake-{name}")
    assert "${" not in text  # templatefile 변수는 위 4개뿐
    return json.loads(text)["States"]


def _next(state: dict) -> list[str]:
    out = [state[k] for k in ("Next", "Default") if k in state]
    out += [c["Next"] for c in state.get("Choices", [])]
    out += [c["Next"] for c in state.get("Catch", [])]
    return out


def _check_transitions(states: dict) -> None:
    for name, state in states.items():
        for target in _next(state):
            assert target in states, f"{name} → {target}"
        for branch in state.get("Branches", []):
            assert branch["StartAt"] in branch["States"]
            _check_transitions(branch["States"])


def test_all_transitions_exist(states):
    _check_transitions(states)


@pytest.mark.parametrize(
    ("task", "failed"), [("Silver", "SilverFailed"), ("MlReady", "MlReadyFailed")]
)
def test_glue_tasks_retry_and_alert(states, task, failed):
    s = states[task]
    assert s["Resource"] == "arn:aws:states:::glue:startJobRun.sync"
    retry = {tuple(r["ErrorEquals"]): r for r in s["Retry"]}
    assert retry[("Glue.ConcurrentRunsExceededException",)]["MaxAttempts"] == 5
    assert retry[("States.ALL",)]["MaxAttempts"] == 1  # FR-013: 재시도 1회
    assert s["Catch"][0]["Next"] == failed
    assert states[failed]["Next"] == "Notify"
    assert set(states[failed]["Result"]) == {"stage", "job", "runs", "rerun_stage"}
    args = s["Parameters"]["Arguments"]
    assert set(args) == {"--start_date.$", "--end_date.$", "--sfn_execution.$"}


def _route(states: dict, stage: str) -> list[str]:
    """Choice만 해석해 성공 경로의 Task 순서를 돌려준다."""
    path, name = [], "Defaults"
    while states[name]["Type"] != "Succeed":
        s = states[name]
        if s["Type"] == "Task":
            path.append(name)
        if s["Type"] == "Choice":
            hit = [c["Next"] for c in s["Choices"] if c["StringEquals"] == stage]
            name = hit[0] if hit else s["Default"]
        else:
            name = s["Next"]
    return path


@pytest.mark.parametrize(
    ("stage", "expected"),
    [("all", ["Silver", "MlReady"]), ("silver", ["Silver"]), ("ml_ready", ["MlReady"])],
)
def test_stage_routes(states, stage, expected):
    assert _route(states, stage) == expected


def test_defaults_merge_input(states):
    expr = states["Defaults"]["Parameters"]["args.$"]
    assert expr.startswith("States.JsonMerge(") and "$$.Execution.Input" in expr
    for key in ('"start_date":"auto"', '"end_date":"auto"', '"stage":"all"'):
        assert key in expr


def _format_args(message: str) -> tuple[int, int]:
    """States.Format('템플릿', 인자…)의 {} 개수와 인자 개수."""
    assert message.startswith("States.Format('")
    template, rest = message[len("States.Format('") :].split("', ", 1)
    return template.count("{}"), len(rest.rstrip(")").split(", "))


def test_notify_detailed_with_raw_fallback(states):
    notify = states["Notify"]
    assert notify["Type"] == "Parallel" and notify["Next"] == "Failed"
    # 자세한 메일이 실패해도(원인이 JSON이 아님 등) 원문 메일은 반드시 간다
    assert notify["Catch"][0]["ErrorEquals"] == ["States.ALL"]
    assert notify["Catch"][0]["Next"] == "NotifyRaw"
    assert states["NotifyRaw"]["Next"] == "Failed"

    branch = notify["Branches"][0]["States"]
    assert branch["ParseCause"]["Parameters"]["run.$"] == "States.StringToJson($.error.Cause)"
    for task in (branch["NotifyDetailed"], states["NotifyRaw"]):
        assert task["Resource"] == "arn:aws:states:::sns:publish"
        params = task["Parameters"]
        assert params["Subject"].isascii()  # SNS 제목은 ASCII만
        placeholders, args = _format_args(params["Message.$"])
        assert placeholders == args
        assert "\n" in params["Message.$"]  # 줄바꿈으로 읽기 좋게
