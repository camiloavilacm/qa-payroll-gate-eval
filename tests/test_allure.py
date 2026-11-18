import json
from pathlib import Path

import pytest

from payroll_gate.allure import export


def test_export_preserves_repeats_and_infrastructure_errors(tmp_path: Path) -> None:
    source = tmp_path / "results.json"
    common = dict(id="fixture", pack="diag", description="Synthetic lookup")
    run = dict(
        model="test",
        prompt_file="sample.txt",
        prompt_hash="hash",
        mode="test",
        planned=5,
        summary={"evaluated": 2, "status": "incomplete"},
        rows=[
            dict(common, repeat=1, passed=True),
            dict(
                common,
                repeat=2,
                passed=False,
                reasons=["PARSE_ERROR"],
                parse_detail="MARKDOWN_FENCE",
            ),
            dict(common, repeat=3, error="ThrottlingException"),
        ],
    )
    source.write_text(json.dumps(run))
    out = tmp_path / "allure-results"
    export([source], out)
    results = [json.loads(f.read_bytes()) for f in out.glob("*-result.json")]
    assert {r["status"] for r in results} == {"passed", "failed", "broken"}
    assert len({r["testCaseId"] for r in results}) == 3
    assert (
        next(r for r in results if r["status"] == "failed")["statusDetails"]["message"]
        == "PARSE_ERROR · MARKDOWN_FENCE"
    )
    assert all((out / a["source"]).exists() for r in results for a in r["attachments"])
    with pytest.raises(FileExistsError):
        export([source], out)


def test_scenario_view_keeps_every_repeat_and_enforces_constraints(
    tmp_path: Path,
) -> None:
    source = tmp_path / "results.json"
    rows = []
    for scenario in ("majority", "blocked", "interrupted"):
        for repeat in range(1, 6):
            passed = repeat <= 3
            row = dict(
                id=scenario,
                repeat=repeat,
                pack="acc",
                description="Synthetic",
                passed=passed,
                reasons=[] if passed else ["BEHAVIOR_FAIL"],
            )
            if scenario == "blocked" and repeat == 4:
                row["reasons"] = ["CONSTRAINT", "UNAUTHORIZED_READ"]
            if scenario == "interrupted" and repeat == 5:
                row["error"] = "ThrottlingException"
            rows.append(row)
    source.write_text(
        json.dumps(
            dict(
                rows=rows,
                repeats=5,
                model="test",
                prompt_file="test",
                prompt_hash="hash",
                mode="test",
                planned=15,
                summary={"evaluated": 14, "status": "incomplete"},
            )
        )
    )
    dest = tmp_path / "out"
    export([source], dest, by_scenario=True)
    results = [json.loads(p.read_bytes()) for p in dest.glob("*-result.json")]
    assert {r["name"]: r["status"] for r in results} == {
        "majority": "passed",
        "blocked": "failed",
        "interrupted": "broken",
    }
    assert all(len(r["steps"]) == 5 for r in results)
    assert all(
        (dest / s["attachments"][0]["source"]).exists()
        for r in results
        for s in r["steps"]
    )
