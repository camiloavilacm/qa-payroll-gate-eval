import pytest

from payroll_gate.diagnostics import parse_shape


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("  ", "EMPTY_FINAL_TEXT"),
        ("<thinking>private</thinking>{}", "VISIBLE_REASONING_PREFIX"),
        ("```json\n{}", "MARKDOWN_FENCE"),
        ("<answer>{}</answer>", "MARKUP_PREFIX"),
        ("Here is the record: {}", "TEXT_BEFORE_OBJECT"),
        ('{"private":1,"private":2}', "DUPLICATE_JSON_KEY"),
        ('{"v":NaN}', "INVALID_JSON_SYNTAX"),
        ("{", "INVALID_JSON_SYNTAX"),
        ("{} trailing secret", "TRAILING_CONTENT"),
        ("[{}]", "NON_OBJECT_JSON"),
    ],
)
def test_safe_detail(raw: str, expected: str) -> None:
    assert parse_shape(raw) == expected


def test_parse_failure_report_preserves_grade_and_redacts_text() -> None:
    from payroll_gate.cli import scenarios
    from payroll_gate.gateway import Data
    from payroll_gate.report import detail
    from payroll_gate.runner import trial

    def call(**options: object) -> Data:
        return {
            "stopReason": "end_turn",
            "output": {
                "message": {
                    "content": [{"text": "<thinking>private payload</thinking>{}"}]
                }
            },
        }

    scenario = next(s for s in scenarios() if s["id"] == "diag_prompt_with_no_id")
    row = trial(call, "test", "test", scenario)
    assert row["reasons"] == ["BEHAVIOR_FAIL", "PARSE_ERROR"]
    assert row["passed"] is False
    assert "VISIBLE_REASONING_PREFIX" in detail(row)
    assert "private payload" not in str(row)
