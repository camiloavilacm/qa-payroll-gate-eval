Payroll-Delay Investigator — v1.4 Showcase Scope
Status: Scope clarification and simplification of v1.3, not a replacement for its existing domain/test contracts.
1. The single goal
Build a small, runnable demonstration where a developer can change the Amazon Bedrock Converse model (model ID or inference-profile ARN) and system prompt, run the same fictional payroll investigation scenarios, and immediately see how the results differ.

This is a portfolio/showcase project, not a production payroll product, enterprise AI platform, complete CI/CD system, or general-purpose agent-evaluation framework. “Ready” means another developer can clone it, configure AWS access, run an evaluation, change one input, and inspect a fair comparison with minimal setup.
The developer experience (required)
1. Clone the repository and install dependencies.
2. Configure AWS credentials/region using the normal AWS SDK credential chain.
3. Choose a Bedrock model or inference-profile ARN and a local prompt file.
4. Run the same 20 synthetic test scenarios against that configuration.
5. Open a local HTML report and/or read the terminal summary.
6. Change only the model or prompt, rerun, and compare the two runs side by side.
Critical distinction: Offline cassette tests verify the test machinery; they cannot measure a newly selected model or modified prompt. To compare models or prompts, invoke live Bedrock. Never label cassette results as live model performance.
2. Minimal user-facing commands (illustrative CLI contract)
# Verify the local evaluation code; no AWS credentials or network needed
make check

# Real-model evaluations using fictional fixtures
python -m payroll_gate eval \
  --model-id "$BEDROCK_MODEL_ID" \
  --prompt-file prompts/baseline.txt \
  --repeats 1 \
  --output runs/baseline

python -m payroll_gate eval \
  --model-id "$BEDROCK_MODEL_ID" \
  --prompt-file prompts/candidate.txt \
  --repeats 1 \
  --output runs/candidate

# Generate a local side-by-side comparison
python -m payroll_gate compare \
  runs/baseline/results.json \
  runs/candidate/results.json \
  --output runs/comparison.html
--model-id accepts a Bedrock Converse-supported model ID or inference-profile ARN, subject to AWS region, access, and model capabilities. The model may be changed per run; do not hardcode a single ARN in suite.json. Support --region or the normal AWS region configuration. No need for a web application or user database.

For a quick development run, use --repeats 1. For variability evaluation, use --repeats 5 (the v1.3 five-repeat rules and Wilson statistic apply only to this comparable five-repeat mode; do not calculate the locked 50-trial Wilson gate on a 10-trial one-repeat run). Clearly label the modes as quick exploratory run versus five-repeat evaluation. Neither is an unconditional production certification.
3. Keep from v1.3 (minimal core)
- Twenty fixed scenarios: 10 accuracy + 10 diagnostic, with synthetic payroll fixtures and approved target labels. Do not expand the scenario pack for the showcase.
- Safe mock tools: three read tools that return synthetic fixture data; three forbidden write tools that always deny. Never connect to actual payroll services.
- Converse runner: model conversation, proper toolUseId/`toolResult` pairing, bounded turns/tool calls, clear Bedrock errors, and configurable model/prompt.
- Deterministic grading: output JSON/schema validity, expected label, required evidence reads, unauthorized reads, forbidden writes, and basic grounded-entity checks. Report what failed and why.
- Independent expected outcomes: evaluate against scenario expectations that are not generated from the candidate model answer.
- Offline unit/contract tests (make check): Python 3.11, Ruff, strict Mypy and Pytest as already specified. A small reviewed cassette set may remain to exercise protocol/replay; offline checks must not create AWS clients or rewrite approved goldens.
- Results persisted per run: avoid overwriting past results. Save actual prompt/model/config identities, scenario outcomes, and enough sanitized diagnostics to reproduce comparisons.
4. Result report — the centerpiece of the demo
Create results.json and a standalone local report.html for each live evaluation. The HTML needs no backend, database, frontend framework, or hosting.

At minimum show:
Summary	Per-scenario detail	Comparison
Model, prompt file/hash, timestamp, region, repeats	Scenario ID and description	Baseline vs candidate model and prompt
Passed/total and label accuracy	Expected vs predicted label	Overall accuracy delta
Safety violations and missing required reads	Tool sequence and reason codes	Scenarios improved, regressed, unchanged
Bedrock failures (separate from model mistakes)	Redacted trace/short explanation	Safety and missing-evidence deltas
Tokens, latency; estimated cost only if pricing is explicitly supplied	Pass/fail per repeat	Tokens/latency deltas


Do not fabricate prices. Token usage/latency should use actual Bedrock response metadata when available. A run must state when it is incomplete and avoid misleading percentages. Redact secrets, credentials, and account identifiers from persisted diagnostics; keep fixture data fictional.

Comparisons should use the same scenario pack and grader/version. If these differ, flag the comparison as not directly comparable rather than showing an authoritative improvement claim. Show the actual model/prompt fingerprint for every run. If the baseline uses one repeat and candidate uses five, label the repeat-count mismatch.
5. Minimal repo structure
payroll-delay-investigator/
  README.md
  pyproject.toml
  Makefile
  prompts/
    baseline.txt
    candidate.txt
  scenarios/
    ...20 YAML scenarios...
  src/payroll_gate/
    cli.py
    runner.py
    gateway.py
    graders.py
    report.py
    schemas/
      tools.json
      responses.json
      output_contract.json
  tests/
    test_gateway.py
    test_grading.py
    test_converse_protocol.py
    test_cli.py
  runs/                  # gitignored; generated results
May reuse extra v1.3 modules already implemented; do not create abstractions or services solely to support hypothetical expansion. Prefer a few clear Python modules and straightforward tests.
6. Explicitly out of scope
- Production employee/payroll integration or use of real personal/financial records.
- Production authentication and RBAC; tenant and authorization tests remain synthetic test behaviors.
- Terraform/CDK, Kubernetes, ECS, server hosting, persistent database, API gateway, multi-user UI.
- Enterprise dashboards, CloudWatch alerting, incident rotations, retention automation, security certification.
- Nightly scheduling, merge-blocking release policies, approval workflows, production rollback automation.
- Large adversarial test catalogs, human-in-the-loop review, LLM-as-judge, RAG, fine-tuning, automated prompt optimization.
- Guaranteed universal support across every Bedrock model. Handle model incompatibility with an understandable error.
7. Showcase acceptance criteria (definition of done)
A new developer can:
1. Follow the README to set up Python/AWS environment and run make check offline successfully.
2. Point the CLI to model A + prompt A, run the 20 fictional scenarios live, and get a self-contained results.json and report.html.
3. Change only the prompt or model, run again, and see different evaluation artifacts without modifying code.
4. Compare the two runs with one command and inspect correct/incorrect labels, skipped evidence reads, blocked forbidden calls, and execution/usage metadata.
5. Understand and reproduce failures from clear reason codes, without exposing sensitive AWS information.
6. Run a five-repeat evaluation optionally and see repeat consistency and the retained v1.3 Wilson metric, clearly explained as limited evidence—not proof of real-world readiness.
Success criterion: “Change model or prompt → run the same tests → understand what changed.” Everything else serves this workflow or is excluded.