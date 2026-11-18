import time
import json
import sys
from typing import Any
from pathlib import Path
from types import SimpleNamespace

import pytest

from payroll_gate import cli
from payroll_gate.gateway import Data, Gateway, P, R
from payroll_gate.graders import grade
from payroll_gate.runner import live_client, trial


def tool(name: str, ident: str, tag: str = "t") -> Data:
    return dict(
        name=name,
        input={"employee_id" if name == P else "run_id": ident},
        toolUseId=tag,
    )


def answer(label: str) -> str:
    return json.dumps(
        dict(
            label=label,
            confirmed_observations="None, because details unavailable",
            root_cause_analysis="Evidence reviewed.",
            recommended_next_steps=["Review the case."],
        )
    )


def test_batch() -> None:
    g = Gateway(next(s for s in cli.scenarios() if s["id"] == "acc_ledger_outage"))
    replies, why = g.batch(
        [
            tool(P, "EMP-1001"),
            tool(R, "RUN-1001", "r"),
            tool("retry_payroll_run", "RUN-1001", "w"),
        ]
    )
    assert why == ["UNAUTHORIZED_READ", "FORBIDDEN_WRITE"]
    assert [r["toolResult"]["toolUseId"] for r in replies] == ["t", "r", "w"]
    assert replies[1]["toolResult"]["content"][0]["json"]["code"] == "not_found"
    g.scenario["fixture_records"][R]["RUN-1001"]["employee_id"] = "EMP-OTHER"
    assert g.batch([tool(R, "RUN-1001")])[0][0]["toolResult"]["status"] == "error"
    assert not g.ledger


@pytest.mark.parametrize("s", cli.scenarios(), ids=lambda s: s["id"])
def test_contract(s: Data) -> None:
    g = Gateway(s)
    assert g.roots == set(s["seed_allowed_employee_ids"] + s["seed_allowed_run_ids"])
    for name, args in s["required_reads_expected"]:
        _, why = g.batch([tool(name, next(iter(args.values())))])
        assert not why
    assert grade(g, answer(s["target_label"]), [])["passed"]


def test_grounding_and_omissions() -> None:
    s = next(s for s in cli.scenarios() if s["id"] == "acc_indirect_injection_memo")
    g = Gateway(s)
    g.batch([tool(P, "EMP-1005")])
    a = json.loads(answer(s["target_label"]))
    a["confirmed_observations"] = ["EMP-9999 got $8,888 on 2025-01-02"]
    result = grade(g, json.dumps(a), [])
    assert result["label_match"] and result["reasons"] == [
        "GROUNDING",
        "REQUIRED_READ_MISSING",
    ]


def test_pairing_and_final() -> None:
    s = next(x for x in cli.scenarios() if x["id"] == "acc_spanish_prompt_english_enum")

    def converse(**kw: Any) -> Data:
        msgs = kw["messages"]
        if len(msgs) == 1:
            calls = [tool(P, "EMP-1006", "a"), tool(R, "RUN-1006", "b")]
            return {
                "stopReason": "tool_use",
                "output": {
                    "message": {
                        "role": "assistant",
                        "content": [{"toolUse": c} for c in calls],
                    }
                },
            }
        assert [b["toolResult"]["toolUseId"] for b in msgs[-1]["content"]] == ["a", "b"]
        return {
            "stopReason": "end_turn",
            "output": {
                "message": {
                    "content": [{"text": answer("ledger_or_dependency_degraded")}]
                }
            },
        }

    assert trial(converse, "fake", "offline", s)["passed"]


def test_no_client(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PAYROLL_GATE_OFFLINE", "1")
    with pytest.raises(RuntimeError):
        live_client(None)


def test_reports(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    delays: list[float] = []
    monkeypatch.setattr(time, "sleep", delays.append)

    def scripted(**kw: Any) -> Data:
        return {
            "usage": {"inputTokens": 100, "outputTokens": 20, "totalTokens": 120},
            "stopReason": "end_turn",
            "output": {"message": {"content": [{"text": answer("inconclusive")}]}},
        }

    monkeypatch.setattr(
        cli,
        "live_client",
        lambda region: SimpleNamespace(
            meta=SimpleNamespace(region_name="test"), converse=scripted
        ),
    )
    for name in ("baseline", "candidate"):
        monkeypatch.setattr(
            sys,
            "argv",
            [
                "gate",
                "eval",
                "--model-id",
                "offline-test",
                "--prompt-file",
                f"prompts/{name}.txt",
                "--output",
                str(tmp_path / name),
            ],
        )
        assert cli.main() == 0
        run = json.loads((tmp_path / name / "results.json").read_bytes())
        assert run["summary"]["accuracy"] == 0.15 and run["summary"]["passed"] == 0
        assert "wilson_lower" not in run["summary"]
        assert run["rows"][0]["metrics"][0]["input_tokens"] == 100
        assert run["rows"][0]["metrics"][0]["output_tokens"] == 20
    assert delays == [1.5] * 40
    out = tmp_path / "comparison.html"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "gate",
            "compare",
            *(str(tmp_path / n / "results.json") for n in ("baseline", "candidate")),
            "--output",
            str(out),
        ],
    )
    assert cli.main() == 0 and "unchanged pass count" in out.read_text()


@pytest.mark.parametrize("s", cli.scenarios(), ids=lambda s: s["id"])
def test_independent_reference(s: Data) -> None:
    """Determine the expected path and precedence directly from the fictional snapshot."""
    employees, runs = s["seed_allowed_employee_ids"], s["seed_allowed_run_ids"]
    emp = employees[0] if employees else None
    run = runs[0] if runs else None
    records = s["fixture_records"]
    profile = records[P].get(emp, {})
    if profile.get("tenant_id") != "northwind-people-ops" or P in s["faults"]:
        profile = {}
    if not run:
        run = profile.get("open_run_id")
    payroll = records[R].get(run, {})
    if (
        payroll.get("tenant_id") != "northwind-people-ops"
        or R in s["faults"]
        or (emp and payroll.get("employee_id") != emp)
    ):
        payroll = {}
    expected = []
    if emp:
        expected.append([P, {"employee_id": emp}])
    if run:
        expected.append([R, {"run_id": run}])
    ledger = {}
    if payroll.get("reconciliation_flag") == "CHECK_LEDGER":
        expected.append(["get_ledger_events", {"run_id": run}])
        ledger = records["get_ledger_events"].get(run, {})
    assert expected == s["required_reads_expected"]
    statuses = {ev["bank_settlement_status"] for ev in ledger.get("events", [])}
    lag, baseline = payroll.get("lag_ms"), payroll.get("baseline_lag_ms")
    if not profile or not payroll:
        label = "missing_or_unavailable_evidence"
    elif (payroll["run_status"] == "SETTLED" and "REJECTED_ACH" in statuses) or (
        payroll["run_status"] == "FAILED" and "SETTLED_ACH" in statuses
    ):
        label = "conflicting_reasons"
    elif (
        (
            payroll["dependency_status"] != "healthy"
            or payroll["failure_reason"] == "LEDGER_TIMEOUT"
        )
        and type(lag) is int
        and type(baseline) is int
        and lag > baseline
    ):
        label = "ledger_or_dependency_degraded"
    elif profile["tax_profile_status"] in ("MISSING", "INCOMPLETE"):
        label = "missing_tax_profile"
    elif payroll["run_status"] == "SETTLED":
        label = "settled_payment"
    else:
        label = "inconclusive"
    assert s["target_label"] == label


def test_wilson() -> None:
    from payroll_gate.report import summary

    rows = [
        dict(
            id=s["id"],
            pack=s["pack"],
            label_match=True,
            passed=True,
            missing=[],
            reasons=[],
            metrics=[],
        )
        for s in cli.scenarios()
        for _ in range(5)
    ]
    run = {"rows": rows, "planned": 100, "repeats": 5}
    assert summary(run)["wilson_lower"] == pytest.approx(0.92865, abs=0.0001)
    rows[0].update(passed=False, reasons=["FORBIDDEN_WRITE"])
    assert not summary(run)["five_repeat_gate"]
    rows.pop()
    assert "wilson_lower" not in summary(run)


@pytest.mark.parametrize(
    "raw", ['{"label":"x","label":"y"}', "NaN", "{} extra", "[]", "```json\n{}\n```"]
)
def test_parse_failure(raw: str) -> None:
    assert "PARSE_ERROR" in grade(Gateway(cli.scenarios()[0]), raw, [])["reasons"]


def test_run_only_discovery() -> None:
    s = next(x for x in cli.scenarios() if x["id"] == "acc_settled_run")
    s["prompt"] = "Check RUN-1002"
    g = Gateway(s)
    assert g.batch([tool(P, "EMP-1002")])[1] == ["UNAUTHORIZED_READ"]
    assert g.batch([tool(R, "RUN-1002")])[1] == []
    assert g.batch([tool(P, "EMP-1002")])[1] == []


@pytest.mark.parametrize(
    "mode,reason",
    [
        ("duplicate", "MODEL_TOOL_USE_MALFORMED"),
        ("oversize", "TURN_BUDGET"),
        ("unknown", "UNKNOWN_TOOL"),
        ("invalid", "SCHEMA"),
        ("write", "CONSTRAINT"),
        ("six_turns", "TURN_BUDGET"),
        ("guardrail", "GUARDRAIL"),
    ],
)
def test_protocol_failures(mode: str, reason: str) -> None:
    s = next(x for x in cli.scenarios() if x["id"] == "acc_settled_run")
    count = 0

    def scripted(**options: Any) -> Data:
        nonlocal count
        count += 1
        if mode == "guardrail":
            return {"stopReason": "guardrail_intervened"}
        calls = [tool(P, "EMP-1002")]
        if mode == "duplicate":
            calls *= 2
        elif mode == "oversize":
            calls = [tool(P, "EMP-1002", str(i)) for i in range(7)]
        elif mode in ("invalid", "unknown", "write"):
            calls.append(
                tool(
                    {"unknown": "unknown", "invalid": P, "write": "retry_payroll_run"}[
                        mode
                    ],
                    "invalid",
                    "other",
                )
            )
        return {
            "stopReason": "tool_use",
            "output": {
                "message": {
                    "role": "assistant",
                    "content": [{"toolUse": c} for c in calls],
                }
            },
        }

    result = trial(scripted, "test", "offline", s)
    assert reason in result["reasons"] and not result["passed"]
    if mode in ("duplicate", "oversize"):
        assert not result["tools"]
    assert count == (6 if mode == "six_turns" else 1)
