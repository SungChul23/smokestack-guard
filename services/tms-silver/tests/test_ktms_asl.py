"""상태 머신 정의 (T022). spec 008 FR-012·013, research R8."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

ASL = Path(__file__).resolve().parents[3] / "infra/stacks/tms-silver/ktms_pipeline.asl.json"


@pytest.fixture(scope="module")
def states() -> dict:
    text = ASL.read_text(encoding="utf-8")
    for name in (
        "silver_job",
        "ml_ready_job",
        "topic_arn",
        "bucket",
        "check_function",
        "check_mode",
    ):
        assert f"${{{name}}}" in text
        text = text.replace(f"${{{name}}}", f"fake-{name}")
    assert "${" not in text  # templatefile 변수는 위 6개뿐
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
    common = {"--start_date.$", "--end_date.$", "--sfn_execution.$"}
    extra = {
        "Silver": {"--source_prefix.$", "--silver_table.$", "--runs_prefix.$"},
        "MlReady": {"--silver_table.$", "--ml_ready_table.$", "--runs_prefix.$", "--data_source.$"},
    }[task]
    assert set(args) == common | extra  # 011: 출처별 경로·테이블은 RouteSource가 정한 $.src에서


def _route(states: dict, values: dict) -> tuple[list[str], str]:
    """Choice만 해석해 Task 순서와 끝 상태(Succeed·Fail 이름)를 돌려준다. values: JSONPath → 값."""
    path, name = [], "Defaults"
    while states[name]["Type"] not in ("Succeed", "Fail"):
        s = states[name]
        if s["Type"] == "Task":
            path.append(name)
        if s["Type"] == "Choice":
            hit = []
            for c in s["Choices"]:
                want = c.get("StringEquals", c.get("BooleanEquals"))
                if values.get(c["Variable"]) == want:
                    hit.append(c["Next"])
            name = hit[0] if hit else s["Default"]
        else:
            name = s["Next"]
    return path, name


PASSED = {"$.check.result": "passed", "$.args.notify": True, "$.check.block": False}


@pytest.mark.parametrize(
    ("stage", "expected"),
    [
        ("all", ["Silver", "MlReady", "Check"]),
        ("silver", ["Silver"]),
        ("ml_ready", ["MlReady", "Check"]),
        ("check", ["Check"]),  # 010: Glue 잡 없이 검사만
    ],
)
def test_stage_routes(states, stage, expected):
    assert _route(states, PASSED | {"$.args.stage": stage}) == (expected, "Done")


@pytest.mark.parametrize(
    ("result", "notify", "block", "tasks", "end"),
    [
        ("violation", True, False, ["Check", "NotifyCheck"], "Done"),  # observe: 알림만
        ("violation", True, True, ["Check", "NotifyCheck"], "CheckBlocked"),  # block: 실행 실패
        ("violation", False, False, ["Check"], "Done"),  # notify=false: 알림 없음
        ("empty", True, False, ["Check", "NotifyCheck"], "Done"),
    ],
)
def test_check_outcomes(states, result, notify, block, tasks, end):
    values = {
        "$.args.stage": "check",
        "$.check.result": result,
        "$.args.notify": notify,
        "$.check.block": block,
    }
    assert _route(states, values) == (tasks, end)


def test_check_task_retries_and_catches(states):
    s = states["Check"]
    assert s["Resource"] == "arn:aws:states:::lambda:invoke"
    assert s["Parameters"]["FunctionName"] == "fake-check_function"
    assert s["Retry"][-1] == {
        "ErrorEquals": ["States.ALL"],
        "IntervalSeconds": 30,
        "MaxAttempts": 1,
        "BackoffRate": 1,
    }
    assert s["Catch"][0]["Next"] == "CheckFailedNotifyGate"
    assert set(s["ResultSelector"]) == {
        "result.$",
        "block.$",
        "subject.$",
        "message.$",
        "run_record.$",
    }
    assert states["CheckOnly"]["Result"] == {"JobRunId": None}


def test_check_failure_alerts_and_respects_mode(states):
    gate = states["CheckFailedNotifyGate"]
    assert gate["Choices"][0] == {
        "Variable": "$.args.notify",
        "BooleanEquals": False,
        "Next": "CheckFailedOutcome",
    }
    out = states["CheckFailedOutcome"]
    assert out["Choices"][0]["Next"] == "CheckFailedBlocked" and out["Default"] == "Done"
    notify = states["NotifyCheckFailed"]
    assert notify["Catch"][0]["Next"] == "NotifyCheckFailedRaw"
    detailed = notify["Branches"][0]["States"]["NotifyCheckFailedDetailed"]["Parameters"]
    for params in (detailed, states["NotifyCheckFailedRaw"]["Parameters"]):
        assert params["Subject"] == "[tms] K-TMS contract check failed"
        placeholders, args = _format_args(params["Message.$"])
        assert placeholders == args
    # 위반 알림 제목과 실행 실패 알림 제목이 다르다 (FR-007)
    assert states["NotifyCheck"]["Parameters"]["Subject.$"] == "$.check.subject"


def test_mode_cannot_be_overridden_by_input(states):
    expr = states["Defaults"]["Parameters"]["args.$"]
    # 입력을 먼저 합치고 mode를 마지막에 덮어쓴다
    assert expr.index("$$.Execution.Input") < expr.index('"mode"')


def test_defaults_merge_input(states):
    expr = states["Defaults"]["Parameters"]["args.$"]
    assert expr.startswith("States.JsonMerge(") and "$$.Execution.Input" in expr
    for key in ('"start_date":"auto"', '"end_date":"auto"', '"stage":"all"', '"notify":true'):
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


@pytest.mark.parametrize(
    ("source", "state", "prefix", "ml_table", "data_source"),
    [
        (None, "RealSource", "tms_cleansys/", "tms_silver2.ktms_ml_ready", "ktms"),
        (
            "ktms_synth",
            "SynthSource",
            "tms_synthetic_train_v2/",
            "tms_silver2.ktms_synth_ml_ready",
            "ktms_synth",
        ),
    ],
)
def test_source_routes_paths_and_tables(states, source, state, prefix, ml_table, data_source):
    """011: 실측이 기본이고, source=ktms_synth면 합성 경로·테이블·출처와 검사 입력을 쓴다."""
    route = states["RouteSource"]
    hit = [c["Next"] for c in route["Choices"] if c["StringEquals"] == source]
    assert (hit[0] if hit else route["Default"]) == state
    src = states[state]["Parameters"]["src"]
    assert src["source_prefix"] == prefix and src["ml_ready_table"] == ml_table
    assert src["data_source"] == data_source
    assert src["silver_runs"] == "silver2/_runs/" + src["silver_table"].split(".")[1]
    assert src["ml_ready_runs"] == "silver2/_runs/" + ml_table.split(".")[1]
    if source:
        merged = states[state]["Parameters"]["args.$"]
        for key in ("tms_silver2.ktms_synth_ml_ready", "ktms_synth", "tms_silver2.ktms_ml_ready"):
            assert key in merged


def test_real_source_matches_job_defaults():
    """실측 경로의 명시값이 잡 기본값과 같아 008 동작이 바뀌지 않는다."""
    import glue_ktms_ml_ready
    import glue_ktms_silver

    s, m = glue_ktms_silver.parse_args([]), glue_ktms_ml_ready.parse_args([])
    assert (s.source_prefix, s.silver_table, s.runs_prefix) == (
        "tms_cleansys/",
        "tms_silver2.ktms",
        "silver2/_runs/ktms",
    )
    assert (m.ml_ready_table, m.runs_prefix) == (
        "tms_silver2.ktms_ml_ready",
        "silver2/_runs/ktms_ml_ready",
    )
