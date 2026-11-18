"""Export saved evaluation rows to the Allure result-file format."""

import json
from collections import Counter, defaultdict
from pathlib import Path
from uuid import uuid4

from .gateway import Data


def outcome(row: Data) -> str:
    if "error" in row:
        return "Execution error"
    if row["passed"]:
        return "Passed"
    reasons = row.get("reasons", [])
    if "CONSTRAINT" in reasons:
        return "Safety constraint violated"
    if "PARSE_ERROR" in reasons:
        return "Final answer could not be parsed"
    if "SCHEMA" in reasons:
        if any(t["outcome"] == "SCHEMA" for t in row.get("tools", [])):
            return "Invalid tool arguments"
        return "Invalid final answer schema"
    if row.get("predicted") is not None and not row.get("label_match"):
        return "Incorrect label"
    if "REQUIRED_READ_MISSING" in reasons:
        return "Required evidence missing"
    return "Other grading failure"


def scenario_result(entries: list[tuple[Data, Data]], repeats: int) -> Data:
    first = entries[0][1]
    result = first.copy()
    row = entries[0][0]
    counts = Counter(outcome(r) for r, _ in entries)
    passed = counts["Passed"]
    evaluated = len(entries) - counts["Execution error"]
    hard_failure = any(
        set(r.get("reasons", [])) - {"BEHAVIOR_FAIL"} for r, _ in entries
    )
    if evaluated != repeats or counts["Execution error"]:
        status = "broken"
    elif passed >= repeats // 2 + 1 and not hard_failure:
        status = "passed"
    else:
        status = "failed"
    breakdown = " · ".join(f"{reason}: {n}" for reason, n in counts.items())
    result.update(
        name=row["id"],
        fullName=first["fullName"].rsplit(" / ", 1)[0],
        status=status,
        description=f"{row['description']}\n\n{evaluated}/{repeats} evaluated. {breakdown}",
        statusDetails={"message": breakdown},
        parameters=[
            p for p in first["parameters"] if p["name"] not in {"Repeat", "Predicted"}
        ]
        + [{"name": "Repeats passed", "value": f"{passed}/{repeats}"}],
        attachments=first["attachments"][1:],
        steps=[],
    )
    result["testCaseId"] = result["fullName"]
    for r, trial in entries:
        result["steps"].append(
            {
                "name": f"Repeat {r['repeat']} · {outcome(r)} · predicted {r.get('predicted') or 'unavailable'}",
                "status": trial["status"],
                "statusDetails": trial["statusDetails"],
                "steps": trial["steps"],
                "attachments": trial["attachments"][:1],
            }
        )
    return result


def export(paths: list[Path], destination: Path, *, by_scenario: bool = False) -> None:
    runs = [json.loads(path.read_bytes()) for path in paths]
    destination.mkdir(parents=True, exist_ok=False)
    for index, run in enumerate(runs, 1):
        group = f"{index}. {run['prompt_file']} · {run['mode']}"
        summary = {key: value for key, value in run.items() if key != "rows"}
        summary_file = f"{uuid4()}-attachment.json"
        (destination / summary_file).write_text(json.dumps(summary, indent=2))
        rows = run["rows"]
        if not rows:
            rows = [
                dict(
                    id="run setup",
                    repeat=0,
                    pack="setup",
                    description="No trials recorded.",
                    error=run.get("execution_error", "No trial results"),
                )
            ]
        groups: dict[str, list[tuple[Data, Data]]] = defaultdict(list)
        for row in rows:
            uid = str(uuid4())
            full_name = f"{group} / {row['id']} / {row['repeat']}"
            status = (
                "broken" if "error" in row else "passed" if row["passed"] else "failed"
            )
            message = " · ".join(
                filter(
                    None,
                    [
                        row.get("error"),
                        *row.get("reasons", []),
                        row.get("parse_detail"),
                    ],
                )
            )
            row_file = f"{uid}-attachment.json"
            (destination / row_file).write_text(json.dumps(row, indent=2))
            params = {
                "Model": run["model"],
                "Prompt SHA-256": run["prompt_hash"],
                "Repeat": row["repeat"],
                "Expected": row.get("expected"),
                "Predicted": row.get("predicted"),
                "Run coverage": f"{run['summary']['evaluated']}/{run['planned']} evaluated ({run['summary']['status']})",
            }
            steps = []
            for call in row.get("tools", []):
                outcome = call["outcome"]
                steps.append(
                    {
                        "name": f"{call['tool']}({call['id']}) → {outcome}",
                        "status": "failed"
                        if outcome
                        in {
                            "FORBIDDEN_WRITE",
                            "UNAUTHORIZED_READ",
                            "UNKNOWN_TOOL",
                            "SCHEMA",
                        }
                        else "passed",
                    }
                )
            if row.get("missing"):
                steps.append(
                    {
                        "name": f"Missing required reads: {row['missing']}",
                        "status": "failed",
                    }
                )
            result: Data = {
                "uuid": uid,
                "name": f"{row['id']} · repeat {row['repeat']}"
                if row["repeat"]
                else "Run setup",
                "fullName": full_name,
                "testCaseId": full_name,
                "status": status,
                "description": row["description"],
                "statusDetails": {"message": message},
                "parameters": [
                    {"name": k, "value": str(v) if v is not None else "Unavailable"}
                    for k, v in params.items()
                ],
                "labels": [
                    {"name": "parentSuite", "value": group},
                    {"name": "suite", "value": row["pack"]},
                    {"name": "subSuite", "value": row["id"]},
                ],
                "steps": steps,
                "attachments": [
                    {
                        "name": "Recorded trial",
                        "type": "application/json",
                        "source": row_file,
                    },
                    {
                        "name": "Run configuration and scorecard",
                        "type": "application/json",
                        "source": summary_file,
                    },
                ],
            }
            if by_scenario and row["repeat"]:
                groups[row["id"]].append((row, result))
            else:
                (destination / f"{uid}-result.json").write_text(json.dumps(result))
        for entries in groups.values():
            result = scenario_result(entries, run["repeats"])
            (destination / f"{result['uuid']}-result.json").write_text(
                json.dumps(result)
            )
