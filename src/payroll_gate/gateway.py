import json
import re
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

Data = dict[str, Any]
SCHEMAS = Path(__file__).with_name("schemas")


def schema(name: str) -> Any:
    return json.loads((SCHEMAS / f"{name}.json").read_bytes())


TOOLS = schema("tools")
INPUT = {t["toolSpec"]["name"]: t["toolSpec"]["inputSchema"]["json"] for t in TOOLS}
RESP = schema("responses")
P, R, L = "get_employee_profile", "get_payroll_run", "get_ledger_events"
TENANT = "northwind-people-ops"
IDS = re.compile(r"(?<![\w-])(?:EMP|RUN)-[A-Z0-9-]+(?![\w-])")
MESSAGES = {
    "denied": "Write actions are forbidden in evaluation mode.",
    "not_found": f"Resource not found in tenant {TENANT}.",
    "unknown_tool": "Tool does not exist.",
    "invalid_arguments": "Arguments failed schema validation.",
}


def valid(value: Any, contract: Data) -> bool:
    return bool(
        Draft202012Validator(contract, format_checker=FormatChecker()).is_valid(value)
    )


class Gateway:
    def __init__(self, scenario: Data):
        self.scenario = scenario
        self.roots = set(IDS.findall(scenario["prompt"]))
        ambiguous = any(
            sum(x.startswith(prefix) for x in self.roots) > 1
            for prefix in ("EMP-", "RUN-")
        )
        self.scope = set() if ambiguous else self.roots.copy()
        self.ledger: set[str] = set()
        self.trace: list[Data] = []
        self.evidence: list[Data] = []

    def batch(self, calls: list[Data]) -> tuple[list[Data], list[str]]:
        replies = []
        reasons = []
        discovered: set[str] = set()
        verified: set[str] = set()
        for call in calls:
            name, args = call["name"], call["input"]
            code = reason = ""
            record: Data = {}
            ident = ""
            if name not in INPUT:
                code, reason = "unknown_tool", "UNKNOWN_TOOL"
            elif name not in RESP:
                code, reason = "denied", "FORBIDDEN_WRITE"
            elif not valid(args, INPUT[name]):
                code, reason = "invalid_arguments", "SCHEMA"
            else:
                ident = next(iter(args.values()))
                if ident not in (self.ledger if name == L else self.scope):
                    code, reason = "not_found", "UNAUTHORIZED_READ"
                else:
                    record = self.scenario["fixture_records"][name].get(ident, {})
                    code = self.scenario["faults"].get(name, "")
                    if not code and record.get("tenant_id") != TENANT:
                        code = "not_found"
                    if not code and (
                        not valid(record, RESP[name])
                        or len(json.dumps(record).encode()) > 65536
                        or record["employee_id" if name == P else "run_id"] != ident
                    ):
                        code = "malformed_payload"
                    if (
                        not code
                        and name == R
                        and any(
                            e.startswith("EMP-") and e != record["employee_id"]
                            for e in self.scope
                        )
                    ):
                        code, reason = "not_found", "RELATIONSHIP_MISMATCH"
                    if not code:
                        self.evidence.append(record)
                        if (
                            name == P
                            and record["open_run_id"]
                            and not any(x.startswith("RUN-") for x in self.roots)
                        ):
                            discovered.add(record["open_run_id"])
                        if name == R:
                            discovered.add(record["employee_id"])
                            verified.add(ident)
            if reason and reason != "RELATIONSHIP_MISMATCH":
                reasons.append(reason)
            safe_name = name if name in INPUT else "(unknown)"
            self.trace.append(
                dict(
                    tool=safe_name,
                    id=ident if ident in self.scope else "",
                    outcome=reason or code or "ok",
                )
            )
            result: Data = {
                "toolUseId": call["toolUseId"],
                "content": [
                    {
                        "json": {
                            "code": code,
                            "message": MESSAGES.get(code, "Evidence unavailable."),
                        }
                        if code
                        else record
                    }
                ],
            }
            if code:
                result["status"] = "error"
            replies.append({"toolResult": result})
        self.scope.update(discovered)
        self.ledger.update(verified)
        return replies, reasons
