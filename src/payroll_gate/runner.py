import os
import random
import time

from botocore.exceptions import (
    ClientError,
    EndpointConnectionError,
    ConnectTimeoutError,
    ReadTimeoutError,
)
from typing import Any, Callable

from .gateway import TOOLS, Data, Gateway
from .graders import grade

STOPS = dict(
    max_tokens="MAX_TOKENS",
    guardrail_intervened="GUARDRAIL",
    content_filtered="CONTENT_FILTERED",
    malformed_model_output="MODEL_OUTPUT_MALFORMED",
    malformed_tool_use="MODEL_TOOL_USE_MALFORMED",
    model_context_window_exceeded="CONTEXT_WINDOW_EXCEEDED",
    stop_sequence="UNEXPECTED_STOP_SEQUENCE",
)


def live_client(region: str | None) -> Any:
    if os.getenv("PAYROLL_GATE_OFFLINE") == "1":
        raise RuntimeError("Offline mode")
    import boto3
    from botocore.config import Config

    return boto3.client(
        "bedrock-runtime",
        region_name=region,
        config=Config(
            retries={"mode": "standard", "total_max_attempts": 1},
            connect_timeout=10,
            read_timeout=30,
        ),
    )


def request(call: Callable[..., Data], **options: Any) -> tuple[Data, int]:
    transient = {
        "ThrottlingException",
        "ServiceUnavailableException",
        "InternalServerException",
        "ModelNotReadyException",
        "ModelTimeoutException",
    }
    for attempt in range(1, 4):
        try:
            return call(**options), attempt
        except ClientError as exc:
            if attempt == 3 or exc.response["Error"]["Code"] not in transient:
                raise
        except (EndpointConnectionError, ConnectTimeoutError, ReadTimeoutError):
            if attempt == 3:
                raise
        time.sleep(random.uniform(0, 0.5 * 2 ** (attempt - 1)))
    raise AssertionError("unreachable")


def trial(call: Callable[..., Data], model: str, prompt: str, scenario: Data) -> Data:
    gateway = Gateway(scenario)
    messages = [{"role": "user", "content": [{"text": scenario["prompt"]}]}]
    metrics: list[Data] = []
    reasons: list[str] = []
    raw = ""
    for turn in range(6):
        response, attempts = request(
            call,
            modelId=model,
            system=[{"text": prompt}],
            messages=messages,
            toolConfig={"tools": TOOLS},
            inferenceConfig={"maxTokens": 1200},
        )
        metrics.append(
            {
                "attempts": attempts,
                "tokens": response.get("usage", {}).get("totalTokens"),
                "latency_ms": response.get("metrics", {}).get("latencyMs"),
            }
        )
        stop = response.get("stopReason", "")
        msg = response.get("output", {}).get("message", {})
        blocks = msg.get("content", [])
        if stop == "end_turn":
            if any("toolUse" in b for b in blocks):
                reasons.append("MODEL_TOOL_USE_MALFORMED")
            else:
                raw = "".join(b["text"] for b in blocks if "text" in b)
            break
        if stop != "tool_use":
            reasons.append(STOPS.get(stop, "UNKNOWN_STOP_REASON"))
            break
        calls = [b["toolUse"] for b in blocks if "toolUse" in b]
        if (
            not calls
            or any(
                not isinstance(c, dict)
                or not isinstance(c.get("toolUseId"), str)
                or not c["toolUseId"].strip()
                or not isinstance(c.get("name"), str)
                or not isinstance(c.get("input"), dict)
                for c in calls
            )
            or len({c["toolUseId"] for c in calls}) != len(calls)
        ):
            reasons.append("MODEL_TOOL_USE_MALFORMED")
            break
        if len(calls) > 6 or len(gateway.trace) + len(calls) > 12:
            reasons.append("TURN_BUDGET")
            break
        messages.append(msg)
        replies, reasons = gateway.batch(calls)
        messages.append({"role": "user", "content": replies})
        if turn == 5:
            reasons.append("TURN_BUDGET")
        if reasons:
            break
    return dict(**grade(gateway, raw, reasons), metrics=metrics)
