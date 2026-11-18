import argparse
import hashlib
import json
import re
import math
import time
from typing import Any
from datetime import datetime, timezone
from pathlib import Path

from botocore.exceptions import BotoCoreError, ClientError

from .gateway import RESP, SCHEMAS, Data, valid
from .report import comparison, write
from .runner import live_client, trial

ROOT = Path(__file__).parent


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def scenarios() -> list[Data]:
    paths = sorted(Path("scenarios").glob("*.yaml"))
    items = [json.loads(p.read_bytes()) for p in paths]
    if len(items) != 20 or sum(s["pack"] == "acc" for s in items) != 10:
        raise ValueError("Run from the repository root with the 20 showcase scenarios.")
    for s in items:
        for name, records in s["fixture_records"].items():
            if not all(valid(r, RESP[name]) for r in records.values()):
                raise ValueError(f"Invalid fixture in {s['id']}")
    return items


def main() -> int:
    parser = argparse.ArgumentParser(prog="payroll_gate")
    sub = parser.add_subparsers(dest="command", required=True)
    ev = sub.add_parser("eval")
    ev.add_argument("--model-id", required=True)
    ev.add_argument("--region")
    ev.add_argument("--prompt-file", type=Path, required=True)
    ev.add_argument("--repeats", type=int, choices=[1, 5], default=1)
    ev.add_argument(
        "--request-delay",
        type=float,
        default=1.5,
        metavar="SECONDS",
        help="Pause before each Bedrock request (default 1.5 seconds)",
    )
    cmp = sub.add_parser("compare")
    cmp.add_argument("baseline", type=Path)
    cmp.add_argument("candidate", type=Path)
    for command in (cmp, ev):
        command.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "compare":
        rendered = comparison(
            json.loads(args.baseline.read_bytes()),
            json.loads(args.candidate.read_bytes()),
        )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("x") as out:
            out.write(rendered)
        print(args.output)
        return 0
    if not math.isfinite(args.request_delay) or args.request_delay < 0:
        parser.error("--request-delay must be a finite nonnegative number")
    pack = scenarios()
    prompt = args.prompt_file.read_bytes()
    system = prompt.decode()
    args.output.mkdir(parents=True, exist_ok=False)
    run: Data = dict(
        source="live Bedrock",
        model=re.sub(r"\d{12}", "[account]", args.model_id),
        model_hash=digest(args.model_id.encode()),
        prompt_file=args.prompt_file.name,
        prompt_hash=digest(prompt),
        timestamp=datetime.now(timezone.utc).isoformat(),
        region=args.region,
        request_delay_seconds=args.request_delay,
        repeats=args.repeats,
        mode="quick exploratory" if args.repeats == 1 else "five-repeat evaluation",
        pack_hash=digest(json.dumps(pack, sort_keys=True).encode()),
        grader_hash=digest(
            b"".join(
                p.read_bytes()
                for p in sorted(
                    [
                        ROOT / n
                        for n in ("gateway.py", "runner.py", "graders.py", "report.py")
                    ]
                    + list(SCHEMAS.glob("*.json"))
                )
            )
        ),
        planned=20 * args.repeats,
        rows=[],
    )
    try:
        client = live_client(args.region)
        run["region"] = client.meta.region_name
        for scenario in pack:
            for repeat in range(1, args.repeats + 1):
                row = dict(
                    id=scenario["id"],
                    description=scenario["description"],
                    pack=scenario["pack"],
                    expected=scenario["target_label"],
                    repeat=repeat,
                )
                try:
                    usage: list[dict[str, int | None]] = []

                    def converse(**options: Any) -> Data:
                        time.sleep(args.request_delay)
                        response: Data = client.converse(**options)
                        counts = response.get("usage", {})
                        usage.append(
                            {
                                "input_tokens": counts.get("inputTokens"),
                                "output_tokens": counts.get("outputTokens"),
                            }
                        )
                        return response

                    row.update(trial(converse, args.model_id, system, scenario))
                    for metric, counts in zip(row["metrics"], usage, strict=True):
                        metric.update(counts)
                except (BotoCoreError, ClientError) as exc:
                    code = (
                        exc.response["Error"]["Code"]
                        if isinstance(exc, ClientError)
                        else type(exc).__name__
                    )
                    row["error"] = (
                        code if re.fullmatch("[A-Za-z]+", code) else "BedrockError"
                    )
                    run["rows"].append(row)
                    raise
                run["rows"].append(row)
    except (BotoCoreError, ClientError, RuntimeError) as exc:
        run["execution_error"] = type(exc).__name__
        print(
            "Evaluation interrupted. Check SDK credentials, region, connectivity and Converse tool support."
        )
    finally:
        write(run, args.output)
    print(json.dumps(run["summary"], indent=2), args.output / "report.html")
    return 4 if run["summary"]["status"] == "incomplete" else 0
